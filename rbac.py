from functools import wraps
from flask import abort
from flask_login import current_user

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def can_see_ticket(ticket, user):
    """Returns True if the user has access to view the ticket"""
    if user.role == 'admin':
        return True  # Admin can see all tickets
    if user.role == 'manager':
        # Managers can see all tickets in their projects (public and private)
        if ticket.project and ticket.project.team_lead_id == user.id:
            return True  # Manager's own project
        # Managers can see all tickets from projects in their team
        if ticket.project and ticket.project.team_id == user.team_id:
            return True  # Project in manager's team
        # Managers can see public tickets from other projects
        return ticket.public
    if user.role == 'developer':
        return (
            ticket.assignee == user.name or  # assigned to developer
            (ticket.public and ticket.project and ticket.project.team_id == user.team_id)  # public tickets in their team's projects
        )
    if user.role == 'visitor':
        return ticket.public  # Visitors can see all public tickets
    return False

def can_edit_ticket(ticket, user):
    """Returns True if the user has access to modify the ticket"""
    if user.role == 'admin':
        return True  # Admin can edit all tickets
    if user.role == 'manager' and ticket.project and ticket.project.team_lead_id == user.id:
        return True  # Managers can edit tickets in their projects
    if user.role == 'developer' and ticket.assignee == user.name:
        return True  # Developers can edit tickets assigned to them
    return False

def can_manage_team(team, user):
    """Returns True if the user can manage the team"""
    if user.role == 'admin':
        return True  # Admin can manage all teams
    if user.role == 'manager' and team.manager_id == user.id:
        return True  # Manager can manage their own team
    return False

def can_approve_user(team_id, user):
    """Returns True if the user can approve new users for a team"""
    if user.role == 'admin':
        return True  # Admin can approve any user
    if user.role == 'manager':
        from models import Team
        team = Team.query.get(team_id)
        if team and team.manager_id == user.id:
            return True  # Manager can approve users for their team
    # Developers cannot approve users
    return False

def can_reassign_ticket(ticket, user):
    """Returns True if the user can reassign the ticket"""
    if user.role == 'admin':
        return True  # Admin can reassign any ticket
    if user.role == 'manager':
        # Manager can reassign tickets in projects they lead
        if ticket.project and ticket.project.team_lead_id == user.id:
            return True
        # Manager can reassign tickets in their team's projects
        if ticket.project and ticket.project.team_id == user.team_id:
            return True
        if ticket.assignee == user.name:
            return True
    if user.role == 'developer':
        # Developer can reassign tickets assigned to them
        if ticket.assignee == user.name:
            return True
    return False
