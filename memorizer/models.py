from flask import url_for
from sqlalchemy import literal, orm
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy_utils.types.choice import ChoiceType
from sqlalchemy_utils.types.password import PasswordType
from werkzeug.utils import cached_property

from memorizer.database import db
from memorizer.user import get_user


class Course(db.Model):
    __versioned__ = {}
    __tablename__ = 'course'
    __mapper_args__ = {'order_by': 'code'}
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False, info={'label': 'course code'})
    name = db.Column(db.String(120), nullable=False, info={'label': 'name'})
    exams = db.relationship('Exam', backref='course')
    questions = association_proxy('exams', 'questions')

    def __init__(self, code=None, name=None):
        self.code = code
        self.name = name

    @cached_property
    def question_count(self):
        return Question.query\
            .filter_by(course=self).join(Question.exam)\
            .filter(Exam.hidden.is_(False)).count()

    def question(self, id):
        return Question.query\
            .filter_by(course=self)\
            .join(Question.exam)\
            .filter(Exam.hidden.is_(False))\
            .offset(id - 1).limit(1)

    def stats(self):
        from memorizer.utils import generate_stats
        return generate_stats(course_code=self.code)

    def __repr__(self):
        return self.code + ' ' + self.name

    def serialize(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'str': str(self)
        }

    @property
    def string(self):
        return self.code


class Exam(db.Model):
    __versioned__ = {}
    __tablename__ = 'exam'
    __mapper_args__ = {'order_by': 'name'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, info={'label': 'name'})
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    questions = db.relationship('Question', backref='exam')
    multiple_correct = db.Column(db.Boolean, server_default=literal(False), nullable=False, default=False, info={
                                 'label': 'more correct answers per question'})
    hidden = db.Column(db.Boolean, server_default=literal(False), nullable=False, default=False, info={
                                 'label': 'hide', 'admin': True})

    def __init__(self, name=None, course_id=None, multiple_correct=False):
        self.name = name
        self.course_id = course_id
        self.multiple_correct = multiple_correct

    @cached_property
    def question_count(self):
        return Question.query.filter_by(exam=self).count()

    def question(self, id):
        if self.hidden:
            return None
        return Question.query.filter_by(exam=self).offset(id - 1).limit(1)

    def stats(self):
        from memorizer.utils import generate_stats
        return generate_stats(course_code=self.course.code, exam_name=self.name)

    def __repr__(self):
        return self.name

    def serialize(self):
        # Hack to hide hidden exams
        if self.hidden:
            user = get_user()
            if not user.admin:
                return None
        return {
            'id': self.id,
            'name': self.name,
            'course_id': self.course_id,
            'multiple_correct': self.multiple_correct,
        }

    @property
    def string(self):
        return self.course.code + '_' + self.name


class Question(db.Model):
    __versioned__ = {}
    MULTIPLE = '1'
    BOOLEAN = '2'
    TYPES = [
        (MULTIPLE, 'multiple choice'),
        (BOOLEAN, 'yes/no')
    ]
    __tablename__ = 'question'
    __mapper_args__ = {'order_by': 'id'}
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String, info={'label': 'text'})
    image = db.Column(db.String, info={'label': 'picture'})
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'))
    course = association_proxy('exam', 'course')
    reason = db.Column(db.String, info={'label': 'explanation'})

    type = db.Column(ChoiceType(TYPES), info={'label': 'question type'})
    # Boolean question
    correct = db.Column(db.Boolean, info={'label': 'correct'})
    # Alternative question
    alternatives = db.relationship('Alternative', backref='question', order_by='Alternative.id')

    def __init__(self, type=None, text=None, exam_id=None, image="", correct=None):
        self.type = type
        self.text = text
        self.exam_id = exam_id
        self.image = image
        self.correct = correct

    def __repr__(self):
        return self.text

    @property
    def multiple(self):
        return self.type == self.MULTIPLE

    @property
    def choices(self):
        if self.multiple:
            return self.alternatives

    @property
    def index(self):
        return Question.find_index(self)

    @classmethod
    def find_index(cls, question):
        indexes = [q.id for q in cls.query.filter_by(exam_id=question.exam_id).all()]
        return indexes.index(question.id) + 1

    def serialize(self):
        if self.exam.hidden:
            user = get_user()
            if not user.admin:
                return None
        response = {
            'id': self.id,
            'text': self.text,
            'exam_id': self.exam_id,
            'multiple': self.multiple,
            'type': self.type.code
        }
        if self.multiple:
            response['alternatives'] = []
            for alt in self.alternatives:
                alt_dict = alt.serialize()
                del alt_dict['question_id']
                response['alternatives'].append(alt_dict)
        else:
            response['correct'] = self.correct
        if self.image:
            if self.image.startswith('http://'):
                response['image'] = self.image
            else:
                # this is not efficient
                response['image'] = url_for('static', filename='img/' + self.course.code + '/' + self.image)
        return response


class Alternative(db.Model):
    __versioned__ = {}
    __tablename__ = 'alternative'
    __mapper_args__ = {'order_by': 'id'}

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String, info={'label': 'text'})
    correct = db.Column(db.Boolean, info={'label': 'correct'})
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))

    def __init__(self, text=None, correct=None, question_id=None):
        self.text = text
        self.correct = correct
        self.question_id = question_id

    def __repr__(self):
        return self.text

    def serialize(self):
        return {
            'id': self.id,
            'text': self.text,
            'correct': self.correct,
            'question_id': self.question_id
        }


class User(db.Model):
    __tablename__ = 'user'
    __mapper_args__ = {'order_by': 'id'}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, info={'label': 'name'})
    username = db.Column(db.String, unique=True, info={'label': 'username'})
    password = db.Column(PasswordType(schemes=['pbkdf2_sha512']), info={'label': 'password'})
    registered = db.Column(db.Boolean)
    admin = db.Column(db.Boolean)

    def __init__(self):
        self.registered = False
        self.admin = False

    def __repr__(self):
        return self.username


class Stats(db.Model):
    __tablename__ = 'stats'
    __mapper_args__ = {'order_by': 'id'}

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    correct = db.Column(db.Boolean)
    reset = db.Column(db.Boolean)

    question = db.relationship('Question', backref='stats')
    user = db.relationship('User', backref='stats')

    def __init__(self, user, question, correct):
        self.user_id = user.id
        self.question_id = question.id
        self.correct = correct
        self.reset = False

    @classmethod
    def course(cls, user, course_code):
        course_m = Course.query.filter_by(code=course_code).one_or_none()
        questions = Question.query.filter_by(course=course_m)
        return cls.query.filter(
            Stats.reset.is_(False),
            Stats.user_id == user.id,
            Stats.question_id.in_(questions.with_entities(Question.id))
        )

    @classmethod
    def exam(cls, user, course_code, exam_name):
        course_m = Course.query.filter_by(code=course_code).one_or_none()
        exam_m = Exam.query.filter_by(course=course_m, name=exam_name).one_or_none()
        questions = Question.query.filter_by(exam=exam_m)
        return cls.query.filter(
            Stats.reset.is_(False),
            Stats.user_id == user.id,
            Stats.question_id.in_(questions.with_entities(Question.id))
        )

    @classmethod
    def answered(cls, user, question):
        return cls.query.filter_by(user=user, question=question, reset=False).count() > 0


orm.configure_mappers()
