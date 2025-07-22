from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    manager = db.relationship('User', backref='managed_team', foreign_keys=[manager_id])
    users = db.relationship('User', backref='team', lazy=True, foreign_keys='User.team_id')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, manager, developer, visitor
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    approved = db.Column(db.Boolean, default=False, nullable=False)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    team_lead_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='Active')
    
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)  # <-- ADD THIS
    team = db.relationship('Team', backref='projects')  # <-- ADD THIS too

    team_lead = db.relationship('User', backref='leading_projects', foreign_keys=[team_lead_id])


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    priority = db.Column(db.String(50), nullable=False)
    assignee = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='To Do')
    public = db.Column(db.Boolean, default=False, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=True)
    children = db.relationship('Ticket', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    project = db.relationship('Project', backref='tickets')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    user = db.relationship('User', backref='notifications')
