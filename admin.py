from flask import Blueprint, render_template, redirect, url_for, flash
from models import db, User, Team
from flask_login import login_required, current_user
from rbac import role_required, can_approve_user

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/pending_users')
@login_required
@role_required('admin', 'manager')
def pending_users():
    if current_user.role == 'admin':
        # Admin sees all pending users
        users = User.query.filter_by(approved=False).all()
    else:  # Manager
        # Manager sees only pending users for their team
        managed_teams = Team.query.filter_by(manager_id=current_user.id).all()
        team_ids = [team.id for team in managed_teams]
        users = User.query.filter(User.approved==False, User.team_id.in_(team_ids)).all()
    
    return render_template('pending_users.html', pending_users=users)

@admin_bp.route('/approve_user/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin', 'manager')
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Check if manager has permission to approve this user
    if current_user.role == 'manager':
        team = Team.query.get(user.team_id)
        if not team or team.manager_id != current_user.id:
            flash('You do not have permission to approve this user.')
            return redirect(url_for('admin.pending_users'))
    
    user.approved = True
    db.session.commit()
    flash(f'User {user.name} has been approved.')
    return redirect(url_for('admin.pending_users'))

@admin_bp.route('/disapprove_user/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin', 'manager')
def disapprove_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Check if manager has permission to disapprove this user
    if current_user.role == 'manager':
        team = Team.query.get(user.team_id)
        if not team or team.manager_id != current_user.id:
            flash('You do not have permission to disapprove this user.')
            return redirect(url_for('admin.pending_users'))
    
    # Remove user from DB to hide request
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.name} registration request has been disapproved and removed.')
    return redirect(url_for('admin.pending_users'))
