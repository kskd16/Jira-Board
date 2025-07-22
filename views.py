from flask import Blueprint, render_template
from flask_login import login_required

pages_bp = Blueprint('pages', __name__)

@pages_bp.route('/projects')
@login_required
def projects():
    return render_template('projects.html')

@pages_bp.route('/teams')
@login_required
def teams():
    return render_template('teams.html')


@pages_bp.route('/summary')
@login_required
def summary():
    return render_template('summary.html')

@pages_bp.route('/code')
@login_required
def code():
    return render_template('code.html')

@pages_bp.route('/board')
@login_required
def board():
    return render_template('board.html')

@pages_bp.route('/timeline')
@login_required
def timeline():
    return render_template('timeline.html')
