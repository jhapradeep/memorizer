import argparse
import json

from flask_script import Command, Option

from memorizer import models
from memorizer.database import db


class ValidationError(Exception):
    pass


def import_question(question, exam):
    image = question.get('image', '')
    if 'answers' in question:
        question_type = models.Question.MULTIPLE
        answer = None
    else:
        question_type = models.Question.BOOLEAN
        answer = question['answer']
    question_object = models.Question(question_type, question['question'], exam.id, image, answer)
    db.session.add(question_object)
    db.session.commit()
    if question_type != models.Question.MULTIPLE:
        return
    for number, answer in enumerate(question['answers']):
        if type(question['correct']) is int and question['correct'] == number:
            correct = True
        elif type(question['correct']) is list and number in question['correct']:
            correct = True
        else:
            correct = False
        alternative = models.Alternative(answer, correct, question_object.id)
        db.session.add(alternative)
    db.session.commit()


def import_exam(exam_json):
    # Will raise exception if error found
    validate_exam(exam_json)
    # Get or create course
    course = models.Course.query.filter_by(code=exam_json['code']).first()
    if not course:
        course = models.Course(exam_json['code'], exam_json['name'])
        db.session.add(course)
        db.session.commit()
    # Get or create exam
    exam = models.Exam.query.filter_by(name=exam_json['exam'], course=course).first()
    if not exam:
        exam = models.Exam(exam_json['exam'], course.id)
        db.session.add(exam)
        db.session.commit()
    questions = exam_json['questions']
    for question_json in questions:
        import_question(question_json, exam)
    return True


def validate_exam(exam_json):
    # Exam name and course code has to present
    if 'code' not in exam_json:
        raise ValidationError('subject code missing')
    if type(exam_json['code']) is not str:
        raise ValidationError('subject code must be text')
    if len(exam_json['code']) == 0:
        raise ValidationError('subject code cannot be blank')
    if 'name' not in exam_json:
        raise ValidationError('subject name is missing')
    if type(exam_json['name']) is not str:
        raise ValidationError('subject name must be text')
    if len(exam_json['name']) == 0:
        raise ValidationError('subject name cannot be empty')
    if 'exam' not in exam_json:
        raise ValidationError('exam name is missing')
    if type(exam_json['exam']) is not str:
        raise ValidationError('Exam name must be text')
    if len(exam_json['exam']) == 0:
        raise ValidationError('exam name cannot be empty')
    validate_questions(exam_json)


def validate_questions(exam_json):
    if 'questions' not in exam_json:
        raise ValidationError('questions are missing')
    if type(exam_json['questions']) is not list:
        raise ValidationError('questions must be a list')
    if len(exam_json['questions']) == 0:
        raise ValidationError('there must be at least one question')
    questions = exam_json['questions']
    for question in questions:
        try:
            validate_question(question)
        except ValidationError as e:
            # Reraising with more information
            raise ValidationError('{}: {}'.format(e, question.get('question')))


def _validate_alternative(answer):
    if type(answer) is not str:
        raise ValidationError('all options include text')
    if len(answer) == 0:
        raise ValidationError('alternative cannot be empty')


def _validate_correct_answers(answer, length):
    if type(answer) is not int:
        raise ValidationError('Correct answers must be integer or integer list')
    if not (0 <= answer < length):
        raise ValidationError('One of the correct answers does not match any alternatives')


def _validate_multiple_answers(question):
    if type(question['answers']) is not list:
        raise ValidationError('options must be a list')
    if len(question['answers']) < 2:
        raise ValidationError('there must be at least two options')
    if 'correct' not in question:
        raise ValidationError('questions lack correct answers(s)')
    if type(question['correct']) is int:
        answers = [question['correct']]
    elif type(question['correct']) is list:
        answers = question['correct']
    else:
        raise ValidationError('the correct answer must be integer or a list of integers')
    if len(answers) == 0:
        raise ValidationError('there must be at least one correct answer')
    for answer in question['answers']:
        _validate_alternative(answer)
    for answer in answers:
        _validate_correct_answers(answer, len(question['answers']))


def validate_question(question):
    if 'question' not in question:
            raise ValidationError('question text is missing')
    if type(question['question']) is not str:
        raise ValidationError('questions must be text')
    if len(question['question']) == 0:
        raise ValidationError('questions cannot be empty')
    if 'answers' in question:
        # Multiple answers
        _validate_multiple_answers(question)
    elif 'answer' in question:
        # Boolean answer
        if type(question['answer']) is not bool:
            raise ValidationError('answers must be "true" or "false"')
    else:
        raise ValidationError('answers are missing')


class ImportCommand(Command):
    'Import questions in JSON format'

    option_list = (
        Option('filenames', nargs='+', type=argparse.FileType('r'), help='JSON question files'),
    )

    def run(self, filenames):
        print("Importing questions...")
        for filename in filenames:
            exam_json = json.load(filename)
            print('Importing questions from', exam_json['name'], exam_json['code'], 'exam', exam_json['exam'])
            import_exam(exam_json)
        print("Importing completed")
