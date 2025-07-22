# --- Imports and app setup ---
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash
from functools import wraps
from flask import abort
from rbac import can_see_ticket, can_edit_ticket
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_required
from datetime import datetime

from models import db, Ticket, User
from auth import auth_bp
from admin import admin_bp

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'supersecretkey'  # Needed for session and Flask-Login

db.init_app(app)
migrate = Migrate(app, db)

# Helper function to create notifications
def create_notification(user_id, message, link=None):
    from models import Notification
    notification = Notification(
        user_id=user_id,
        message=message,
        link=link,
        read=False,
        created_at=datetime.now()
    )
    db.session.add(notification)
    db.session.commit()
    return notification

# Setup Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Add notifications to all templates
@app.before_request
def before_request():
    from flask import g
    from models import Notification
    
    if current_user.is_authenticated:
        # Get recent notifications
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
        unread_count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
        
        # Add to global context
        g.notifications = notifications
        g.unread_notifications_count = unread_count

@app.context_processor
def inject_notifications():
    from flask import g
    
    # Make notifications available to all templates
    if hasattr(g, 'notifications') and hasattr(g, 'unread_notifications_count'):
        return {
            'notifications': g.notifications,
            'unread_notifications_count': g.unread_notifications_count
        }
    return {
        'notifications': [],
        'unread_notifications_count': 0
    }

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)



# Route for create_ticket page
@app.route('/create_ticket', methods=['GET', 'POST'])
@login_required
def create_ticket():
    from models import User, Team, Ticket, Project
    # Use Flask-Login's current_user directly
    team_members = []
    if current_user.role not in ['admin', 'manager', 'developer'] or current_user.role == 'visitor':
        abort(403)
    if current_user.role == 'developer' and not current_user.team_id:
        flash("You must be in a team to create a ticket.")
        return redirect(url_for('dashboard'))
    if current_user.role == 'manager':
        # Manager can assign to any member of their team
        team_members = User.query.filter_by(team_id=current_user.team_id, approved=True).all()
    elif current_user.role == 'admin':
        # Admin can assign to anyone
        team_members = User.query.filter_by(approved=True).all()
    else:
        # Developer can assign only to self
        team_members = [current_user]
    
    # Get all teams for team selection dropdown
    teams = Team.query.all()
    
    # Get all projects for project selection dropdown
    projects = Project.query.all()
    
    # Get potential parent tickets (epics and features)
    import sqlalchemy as sa
    try:
        # Try to get parent tickets with parent_id column
        parent_tickets = Ticket.query.filter(Ticket.type.in_(['epic', 'feature'])).all()
    except Exception as e:
        print(f"Error getting parent tickets: {e}")
        # If parent_id column doesn't exist, use a custom query
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket WHERE type IN ('epic', 'feature')")
        result = db.session.execute(stmt)
        parent_tickets = []
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            parent_tickets.append(ticket)
    
    if request.method == 'POST':
        from datetime import datetime
        title = request.form['title']
        description = request.form['description']
        type_ = request.form['type']
        priority = request.form['priority']
        team_id = request.form.get('team')
        assignee_id = request.form.get('assignee')
        assignee_user = User.query.get(int(assignee_id)) if assignee_id else None
        assignee_name = assignee_user.name if assignee_user else 'Unknown'
        public_flag = 'public' in request.form
        project_id = request.form.get('project')
        parent_ticket_id = request.form.get('parent_ticket')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        
        # Validate required fields
        if not team_id or not project_id:
            flash('Team and Project are required fields.')
            return redirect(url_for('create_ticket'))
            
        # Ensure project belongs to the selected team
        project = Project.query.get(int(project_id))
        if not project:
            flash('Selected project does not exist.')
            return redirect(url_for('create_ticket'))
            
        # Update project's team to ensure consistency
        project.team_id = int(team_id)
        db.session.commit()
        
        # Create ticket with basic attributes, excluding parent_id
        # Use SQLAlchemy core to avoid ORM issues with missing columns
        from sqlalchemy import Table, MetaData, Column, Integer, String, Text, Boolean, Date
        from sqlalchemy.sql import insert
        
        metadata = MetaData()
        ticket_table = Table('ticket', metadata,
            Column('id', Integer, primary_key=True),
            Column('title', String),
            Column('description', Text),
            Column('type', String),
            Column('priority', String),
            Column('assignee', String),
            Column('status', String),
            Column('public', Boolean),
            Column('project_id', Integer),
            Column('start_date', Date),
            Column('end_date', Date)
        )
        
        # Insert using core API to avoid parent_id column
        stmt = insert(ticket_table).values(
            title=title,
            description=description,
            type=type_,
            priority=priority,
            assignee=assignee_name,
            status='To Do',
            public=public_flag,
            project_id=project_id if project_id else None,
            start_date=start_date,
            end_date=end_date
        )
        
        db.session.execute(stmt)
        db.session.commit()
        flash('Ticket created successfully!')
        return redirect(url_for('board_page'))
    
    return render_template('create_ticket.html', team_members=team_members, projects=projects, parent_tickets=parent_tickets, teams=teams)


# Dummy data for demonstration
people = [
    {"name": "Khushi Dixit", "role": "Developer", "avatar": "https://via.placeholder.com/60"},
    {"name": "Om Verma", "role": "Tester", "avatar": "https://via.placeholder.com/60"}
]
teams = [
    {
        "name": "Team Phoenix",
        "project": "AgriTrek",
        "members": people
    }
]
timeline = [
    {
        "ticket_id": "JIRA-101",
        "title": "Login Page UI",
        "start_date": "2025-07-01",
        "deadline": "2025-07-05",
        "completed_date": "2025-07-04"
    },
    {
        "ticket_id": "JIRA-102",
        "title": "Backend API Setup",
        "start_date": "2025-07-03",
        "deadline": "2025-07-10",
        "completed_date": "2025-07-09"
    }
]
projects = [
    {"name": "AgriTrek", "status": "Active"},
    {"name": "Jira Clone", "status": "Completed"}
]

# Commits data removed

# --- Auth routes ---
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    from models import User
    from werkzeug.security import check_password_hash
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            if not user.approved:
                flash('Your account is pending approval by admin.')
                return redirect(url_for('login'))
            session['logged_in'] = True
            session['user'] = email
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Debug routes
@app.route('/debug/users')
@login_required
def debug_users():
    from models import User
    
    # Only admin can access this debug route
    if current_user.role != 'admin':
        abort(403)
    
    all_users = User.query.all()
    
    return render_template('debug_users.html', users=all_users)

@app.route('/fix-visitors')
@login_required
def fix_visitors():
    from models import User
    
    # Only admin can access this route
    if current_user.role != 'admin':
        abort(403)
    
    # Find all users with role containing 'visitor' (case-insensitive)
    visitors = User.query.filter(User.role.ilike('%visitor%')).all()
    
    # Fix any capitalization issues
    fixed_count = 0
    for user in visitors:
        if user.role != 'visitor':
            print(f"Fixing user {user.name} role from '{user.role}' to 'visitor'")
            user.role = 'visitor'
            fixed_count += 1
    
    db.session.commit()
    
    # Count pending visitors
    pending_visitors = User.query.filter_by(role='visitor', approved=False).all()
    
    flash(f"Fixed {fixed_count} visitor roles. There are now {len(pending_visitors)} pending visitors.")
    return redirect(url_for('admin.pending_users'))

# --- Main app routes (all require login) ---
@app.route('/dashboard')
@login_required
def dashboard():
    from models import Ticket, Project
    import sqlalchemy as sa
    
    # Get tickets for the dashboard
    try:
        # Try to get all tickets with parent_id column
        all_tickets = Ticket.query.all()
    except Exception as e:
        # If parent_id column doesn't exist, use a custom query
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket")
        result = db.session.execute(stmt)
        all_tickets = []
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            all_tickets.append(ticket)
    
    # Filter tickets based on user role
    if current_user.role == 'admin':
        # Admin can see all tickets
        visible_tickets = all_tickets
    elif current_user.role == 'manager':
        # Manager can see all tickets (public and private) from their team's projects
        visible_tickets = []
        for ticket in all_tickets:
            # Check if ticket belongs to a project where the manager is team lead
            if ticket.project and ticket.project.team_lead_id == current_user.id:
                visible_tickets.append(ticket)
            # Check if ticket belongs to a project in the manager's team
            elif ticket.project and ticket.project.team_id == current_user.team_id:
                visible_tickets.append(ticket)
    elif current_user.role == 'developer':
        # Developers can only see their own tickets and public tickets in their team's projects
        visible_tickets = []
        for ticket in all_tickets:
            if ticket.assignee == current_user.name:  # Their own tickets
                visible_tickets.append(ticket)
            elif ticket.public and ticket.project and ticket.project.team_id == current_user.team_id:  # Public tickets in their team
                visible_tickets.append(ticket)
    else:  # Visitor
        # Visitors can see all public tickets
        visible_tickets = [ticket for ticket in all_tickets if ticket.public]
    
    # Organize tickets by status
    tickets = {'To Do': [], 'In Progress': [], 'In Review': [], 'Done': []}
    for t in visible_tickets:
        tickets.setdefault(t.status, []).append(t)
    
    return render_template('index.html', tickets=tickets)

@app.route('/projects', strict_slashes=False)
@login_required
def projects_page():
    from models import Project, User, Team
    import sqlalchemy as sa
    
    # Get filter parameters
    selected_lead_id = request.args.get('team_lead', type=int)
    selected_status = request.args.get('status')
    selected_team_id = request.args.get('team_id', type=int)
    search_query = request.args.get('search', '').strip()
    
    # Get all projects first
    if current_user.role == 'admin':
        all_projects = Project.query.all()
    elif current_user.role == 'manager':
        # Managers can only see projects where they are the team lead
        all_projects = Project.query.filter_by(team_lead_id=current_user.id).all()
    elif current_user.role == 'developer':
        # Developers can see projects for their team
        all_projects = Project.query.filter_by(team_id=current_user.team_id).all()
    else:  # Visitor
        # Visitors can see all projects
        all_projects = Project.query.all()
    
    filtered_projects = all_projects
    
    # Apply filters manually to avoid SQL issues
    if selected_lead_id:
        filtered_projects = [p for p in filtered_projects if p.team_lead_id == selected_lead_id]
    
    if selected_status:
        filtered_projects = [p for p in filtered_projects if p.status == selected_status]
    
    if selected_team_id:
        # Filter by team_id, handling None values
        filtered_projects = [p for p in filtered_projects if getattr(p, 'team_id', None) == selected_team_id]
    
    # Apply search
    if search_query:
        filtered_projects = [p for p in filtered_projects 
                            if (p.name and search_query.lower() in p.name.lower()) or 
                               (p.description and search_query.lower() in p.description.lower())]
    
    # Get data for filter dropdowns
    team_lead_ids = {project.team_lead_id for project in all_projects if project.team_lead_id}
    team_leads = User.query.filter(User.id.in_(team_lead_ids)).all() if team_lead_ids else []
    
    # Get all statuses
    statuses = {project.status for project in all_projects if project.status}
    
    # Get all teams
    teams = Team.query.all()
    
    from datetime import datetime
    
    return render_template('projects.html', 
                          projects=filtered_projects, 
                          team_leads=team_leads, 
                          selected_lead_id=selected_lead_id,
                          statuses=statuses,
                          selected_status=selected_status,
                          teams=teams,
                          selected_team_id=selected_team_id,
                          search_query=search_query,
                          now=datetime.now)

@app.route('/teams')
@login_required
def teams_page():
    from models import Team, User
    # Query teams based on user role
    if current_user.role == 'admin':
        # Admin can see all teams
        teams = Team.query.all()
    elif current_user.role == 'manager':
        # Manager can only see teams they manage
        teams = Team.query.filter_by(manager_id=current_user.id).all()
    elif current_user.role == 'developer':
        # Developers can only see their own team
        teams = Team.query.filter_by(id=current_user.team_id).all() if current_user.team_id else []
    else:
        # Visitors can see all teams
        teams = Team.query.all()
    
    teams_dict = {}
    for team in teams:
        teams_dict[team.name] = User.query.filter_by(team_id=team.id, approved=True).all()
    # Flatten people you work with (all approved users)
    people = User.query.filter_by(approved=True).all()
    return render_template('teams.html', teams=teams_dict, people=people)

@app.route('/timeline')
@login_required
def timeline_page():
    from models import Project
    projects = Project.query.all()
    return render_template('timeline.html', projects=projects)

@app.route('/board')
@login_required
def board_page():
    from models import Ticket
    import sqlalchemy as sa
    
    user = current_user
    
    # Use a raw SQL query to avoid the parent_id column
    try:
        # Try to get all tickets with parent_id column
        all_tickets = Ticket.query.all()
    except Exception as e:
        # If parent_id column doesn't exist, use a custom query
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket")
        result = db.session.execute(stmt)
        all_tickets = []
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            all_tickets.append(ticket)
    
    # Filter tickets based on user role
    if user.role == 'admin':
        # Admin can see all tickets
        visible_tickets = all_tickets
    elif user.role == 'manager':
        # Manager can see all tickets (public and private) from their team's projects
        visible_tickets = []
        for ticket in all_tickets:
            # Check if ticket belongs to a project where the manager is team lead
            if ticket.project and ticket.project.team_lead_id == user.id:
                visible_tickets.append(ticket)
            # Check if ticket belongs to a project in the manager's team
            elif ticket.project and ticket.project.team_id == user.team_id:
                visible_tickets.append(ticket)
    else:
        # Developers can only see their own tickets and public tickets in their team's projects
        visible_tickets = []
        for ticket in all_tickets:
            if ticket.assignee == user.name:  # Their own tickets
                visible_tickets.append(ticket)
            elif ticket.public and ticket.project and ticket.project.team_id == user.team_id:  # Public tickets in their team
                visible_tickets.append(ticket)
    
    tickets = {'To Do': [], 'In Progress': [], 'In Review': [], 'Done': []}
    for t in visible_tickets:
        tickets.setdefault(t.status, []).append(t)
    return render_template('board.html', tickets=tickets)

@app.route('/all_tickets')
@login_required
def all_tickets():
    from models import Ticket
    import sqlalchemy as sa
    
    # Only admin can see all tickets
    if current_user.role != 'admin':
        abort(403)
    
    # Use a raw SQL query to avoid the parent_id column
    try:
        # Try to get all tickets with parent_id column
        tickets = Ticket.query.all()
    except Exception as e:
        # If parent_id column doesn't exist, use a custom query
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket")
        result = db.session.execute(stmt)
        tickets = []
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            tickets.append(ticket)
    
    return render_template('all_tickets.html', tickets=tickets)

# API endpoint for updating ticket status
@app.route('/api/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
def api_ticket_status(ticket_id):
    from models import Ticket
    from rbac import can_edit_ticket
    
    data = request.get_json()
    new_status = data.get('status')
    ticket = Ticket.query.get_or_404(ticket_id)
    
    # Check if user has permission to edit this ticket
    if not can_edit_ticket(ticket, current_user):
        return jsonify({"status": "error", "message": "Permission denied"}), 403
    
    if new_status and new_status in ['To Do', 'In Progress', 'In Review', 'Done']:
        old_status = ticket.status
        ticket.status = new_status
        db.session.commit()
        
        # Find the assignee user to send notification
        assignee_user = User.query.filter_by(name=ticket.assignee).first()
        if assignee_user:
            # Create notification for status change
            create_notification(
                user_id=assignee_user.id,
                message=f'Ticket "{ticket.title}" status changed from {old_status} to {new_status}',
                link=url_for('board_page')
            )
        
        return jsonify({"status": "success", "message": "Ticket status updated"})
    else:
        return jsonify({"status": "error", "message": "Invalid status"}), 400

@app.route('/api/ticket/<int:ticket_id>/children')
@login_required
def api_ticket_children(ticket_id):
    from models import Ticket
    from rbac import can_see_ticket
    
    ticket = Ticket.query.get_or_404(ticket_id)
    
    # Check if user has permission to see this ticket
    if not can_see_ticket(ticket, current_user):
        return jsonify({"status": "error", "message": "Permission denied"}), 403
    
    # Get all child tickets if the relationship exists
    children = []
    try:
        if hasattr(ticket, 'children'):
            for child in ticket.children:
                if can_see_ticket(child, current_user):
                    children.append({
                        "id": child.id,
                        "title": child.title,
                        "type": child.type,
                        "priority": child.priority,
                        "status": child.status,
                        "assignee": child.assignee
                    })
    except Exception as e:
        print(f"Error getting children: {e}")
    
    return jsonify({
        "parent": {
            "id": ticket.id,
            "title": ticket.title,
            "type": ticket.type
        },
        "children": children
    })

@app.route('/summary')
@login_required
def summary_page():
    from models import Ticket, Team, Project, User
    from collections import defaultdict
    from datetime import datetime, timedelta
    import sqlalchemy as sa
    
    user = current_user
    
    # Use a raw SQL query to avoid the parent_id column
    try:
        # Try to get all tickets with parent_id column
        tickets = Ticket.query.all()
    except Exception as e:
        # If parent_id column doesn't exist, use a custom query
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket")
        result = db.session.execute(stmt)
        tickets = []
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            tickets.append(ticket)
    
    # Filter tickets based on user role
    if user.role == 'admin':
        # Admin can see all tickets
        filtered = tickets
    elif user.role == 'manager':
        # Manager can see all tickets from their team's projects
        filtered = []
        for ticket in tickets:
            # Check if ticket belongs to a project where the manager is team lead
            if ticket.project and ticket.project.team_lead_id == user.id:
                filtered.append(ticket)
            # Check if ticket belongs to a project in the manager's team
            elif ticket.project and ticket.project.team_id == user.team_id:
                filtered.append(ticket)
    else:
        # Developers can only see their own tickets and public tickets in their team's projects
        filtered = []
        for ticket in tickets:
            if ticket.assignee == user.name:  # Their own tickets
                filtered.append(ticket)
            elif ticket.public and ticket.project and ticket.project.team_id == user.team_id:  # Public tickets in their team
                filtered.append(ticket)
    
    # Basic ticket counts
    total_tickets = len(filtered)
    completed_tickets = len([t for t in filtered if t.status == 'Done'])
    
    # Status distribution
    status_data = defaultdict(int)
    for t in filtered:
        status_data[t.status] += 1
    
    # Priority distribution
    priority_data = defaultdict(int)
    for t in filtered:
        priority_data[t.priority] += 1
    
    # Type distribution
    type_data = defaultdict(int)
    for t in filtered:
        type_data[t.type] += 1
    
    # Team data (for admin and managers)
    team_data = {}
    timeline_data = {'labels': [], 'completed': [], 'created': []}
    
    if user.role in ['admin', 'manager']:
        # Team performance data
        teams = Team.query.all()
        for team in teams:
            team_tickets = [t for t in filtered if t.project and t.project.team_id == team.id]
            if team_tickets:
                team_data[team.name] = {
                    'total': len(team_tickets),
                    'completed': len([t for t in team_tickets if t.status == 'Done'])
                }
        
        # Timeline data (last 7 days)
        today = datetime.now().date()
        for i in range(7):
            day = today - timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            timeline_data['labels'].insert(0, day_str)
            
            # This is simplified - in a real app you'd track creation/completion dates
            # For demo purposes, we'll use random data
            import random
            timeline_data['completed'].insert(0, random.randint(0, 5))
            timeline_data['created'].insert(0, random.randint(1, 8))
    
    return render_template('summary.html', 
                           total_tickets=total_tickets, 
                           completed_tickets=completed_tickets,
                           status_data=dict(status_data),
                           priority_data=dict(priority_data),
                           type_data=dict(type_data),
                           team_data=team_data,
                           timeline_data=timeline_data)

# GitHub integration removed

@app.route('/notifications')
@login_required
def notifications_page():
    from models import Notification
    
    # Get user's notifications, ordered by newest first
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications.html', notifications=notifications)

@app.route('/notifications/mark_all_read')
@login_required
def mark_all_read():
    from models import Notification
    
    # Mark all user's notifications as read
    notifications = Notification.query.filter_by(user_id=current_user.id, read=False).all()
    for notification in notifications:
        notification.read = True
    
    db.session.commit()
    flash('All notifications marked as read')
    
    return redirect(url_for('notifications_page'))

@app.route('/notifications/<int:notification_id>/read')
@login_required
def mark_notification_read(notification_id):
    from models import Notification
    
    # Mark specific notification as read
    notification = Notification.query.get_or_404(notification_id)
    
    # Ensure user can only mark their own notifications
    if notification.user_id != current_user.id:
        abort(403)
    
    notification.read = True
    db.session.commit()
    
    return redirect(url_for('notifications_page'))

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def api_mark_notifications_read():
    from models import Notification
    
    # Mark all user's notifications as read via API
    notifications = Notification.query.filter_by(user_id=current_user.id, read=False).all()
    for notification in notifications:
        notification.read = True
    
    db.session.commit()
    
    return jsonify({"status": "success", "message": "All notifications marked as read"})

@app.route('/hierarchy')
@login_required
def hierarchy_page():
    # Visitors cannot access this page
    if current_user.role == 'visitor':
        abort(403)
    from models import Ticket
    import sqlalchemy as sa
    
    # Use raw SQL to avoid parent_id column issues
    try:
        # Get all tickets by type
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket")
        result = db.session.execute(stmt)
        
        # Organize tickets by type
        epics = []
        features = []
        stories = []
        
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            
            if ticket.type == 'epic':
                epics.append(ticket)
            elif ticket.type == 'feature':
                features.append(ticket)
            else:  # story, task, bug
                stories.append(ticket)
        
        return render_template('hierarchy.html', epics=epics, features=features, stories=stories)
    except Exception as e:
        # Log the error but don't show it to the user
        print(f"Hierarchy error: {e}")
        return render_template('hierarchy.html', epics=[], features=[], stories=[], error=True)

@app.route('/search')
@login_required
def search():
    from models import Ticket, Project, User, Team
    import sqlalchemy as sa
    
    query = request.args.get('q', '').strip()
    if not query:
        return render_template('search_results.html', results=[], query='')
    
    # Search results containers
    tickets = []
    projects = []
    users = []
    teams = []
    
    # Search tickets
    try:
        # Try with parent_id column
        ticket_results = Ticket.query.filter(
            sa.or_(
                Ticket.title.ilike(f'%{query}%'),
                Ticket.description.ilike(f'%{query}%'),
                Ticket.assignee.ilike(f'%{query}%'),
                Ticket.type.ilike(f'%{query}%')
            )
        ).all()
        tickets = [t for t in ticket_results if can_see_ticket(t, current_user)]
    except Exception as e:
        # If parent_id column doesn't exist, use raw SQL
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket WHERE title LIKE :query OR description LIKE :query OR assignee LIKE :query OR type LIKE :query")
        result = db.session.execute(stmt, {"query": f'%{query}%'})
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            if can_see_ticket(ticket, current_user):
                tickets.append(ticket)
    
    # Search projects
    projects = Project.query.filter(
        sa.or_(
            Project.name.ilike(f'%{query}%'),
            Project.description.ilike(f'%{query}%'),
            Project.status.ilike(f'%{query}%')
        )
    ).all()
    
    # Search users (only for admin and managers)
    if current_user.role in ['admin', 'manager']:
        users = User.query.filter(
            sa.or_(
                User.name.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%'),
                User.role.ilike(f'%{query}%')
            )
        ).all()
    
    # Search teams
    teams = Team.query.filter(Team.name.ilike(f'%{query}%')).all()
    
    # Combine results
    results = {
        'tickets': tickets,
        'projects': projects,
        'users': users,
        'teams': teams
    }
    
    return render_template('search_results.html', results=results, query=query)

# --- API endpoints (optional, not protected) ---
@app.route('/create_team', methods=['GET', 'POST'])
@login_required
def create_team():
    from models import User, Team
    from rbac import role_required
    
    # Only admin can create teams
    if current_user.role != 'admin':
        abort(403)
    
    if request.method == 'POST':
        name = request.form.get('name')
        manager_id = request.form.get('manager_id')
        member_ids = request.form.getlist('members[]')
        
        # Create new team
        team = Team(name=name, manager_id=manager_id)
        db.session.add(team)
        db.session.commit()
        
        # Assign members to team
        if member_ids:
            for member_id in member_ids:
                user = User.query.get(int(member_id))
                if user:
                    user.team_id = team.id
            db.session.commit()
        
        flash(f'Team {name} created successfully!')
        return redirect(url_for('teams_page'))
    
    # Get managers and developers for form dropdowns
    managers = User.query.filter_by(role='manager', approved=True).all()
    developers = User.query.filter_by(role='developer', approved=True).all()
    return render_template('create_team.html', managers=managers, developers=developers)

@app.route('/team/<int:team_id>/pending_users')
@login_required
def team_pending_users(team_id):
    from models import User, Team
    from rbac import can_approve_user
    
    team = Team.query.get_or_404(team_id)
    
    # Check if user can approve for this team
    if not can_approve_user(team_id, current_user):
        abort(403)
    
    # Get pending users for this team
    pending_users = User.query.filter_by(team_id=team_id, approved=False).all()
    
    # For managers, filter to only show developers (not other managers)
    if current_user.role == 'manager':
        pending_users = [user for user in pending_users if user.role == 'developer']
    
    # For managers, filter out visitors - they are approved by admin only
    if current_user.role == 'manager':
        pending_users = [user for user in pending_users if user.role != 'visitor']
    
    return render_template('pending_users.html', pending_users=pending_users, team=team)

# Visitor approval is now handled through the regular admin.pending_users route

@app.route('/team/<int:team_id>/approve_user/<int:user_id>', methods=['POST'])
@login_required
def team_approve_user(team_id, user_id):
    from models import User, Team
    from rbac import can_approve_user
    
    if not can_approve_user(team_id, current_user):
        abort(403)
    
    user = User.query.get_or_404(user_id)
    if user.team_id != team_id:
        abort(400)  # Bad request if user is not in this team
    
    user.approved = True
    db.session.commit()
    
    # Create notification for the approved user
    create_notification(
        user_id=user.id,
        message=f'Your account has been approved for team {user.team.name}',
        link=url_for('dashboard')
    )
    
    flash(f'User {user.name} has been approved.')
    return redirect(url_for('team_pending_users', team_id=team_id))

@app.route('/team/<int:team_id>/disapprove_user/<int:user_id>', methods=['POST'])
@login_required
def team_disapprove_user(team_id, user_id):
    from models import User, Team
    from rbac import can_approve_user
    
    if not can_approve_user(team_id, current_user):
        abort(403)
    
    user = User.query.get_or_404(user_id)
    if user.team_id != team_id:
        abort(400)  # Bad request if user is not in this team
    
    # Remove user from DB to hide request
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.name} registration request has been disapproved and removed.')
    return redirect(url_for('team_pending_users', team_id=team_id))

@app.route('/ticket/<int:ticket_id>/reassign', methods=['GET', 'POST'])
@login_required
def reassign_ticket(ticket_id):
    from models import Ticket, User
    from rbac import can_reassign_ticket
    import sqlalchemy as sa
    
    # Get ticket without using ORM to avoid parent_id column
    stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket WHERE id = :ticket_id")
    result = db.session.execute(stmt, {"ticket_id": ticket_id}).fetchone()
    
    if not result:
        abort(404)
    
    # Create a ticket object manually
    ticket = Ticket(
        id=result.id,
        title=result.title,
        description=result.description,
        type=result.type,
        priority=result.priority,
        assignee=result.assignee,
        status=result.status,
        public=result.public,
        project_id=result.project_id,
        start_date=result.start_date,
        end_date=result.end_date
    )
    
    # Check permissions
    if not can_reassign_ticket(ticket, current_user):
        abort(403)
    
    if request.method == 'POST':
        new_assignee_id = request.form.get('assignee_id')
        if not new_assignee_id:
            flash('No assignee selected')
            return redirect(url_for('board_page'))
        
        new_assignee = User.query.get(int(new_assignee_id))
        if not new_assignee:
            flash('Invalid assignee')
            return redirect(url_for('board_page'))
        
        # Update assignee using raw SQL to avoid parent_id column
        update_stmt = sa.text("UPDATE ticket SET assignee = :assignee WHERE id = :ticket_id")
        db.session.execute(update_stmt, {"assignee": new_assignee.name, "ticket_id": ticket_id})
        db.session.commit()
        
        # Create notification for the new assignee
        create_notification(
            user_id=new_assignee.id,
            message=f'You have been assigned ticket: {ticket.title}',
            link=url_for('board_page')
        )
        
        flash(f'Ticket reassigned to {new_assignee.name}')
        return redirect(url_for('board_page'))
    
    # GET request - show reassign form
    # Get team members who can be assigned
    team_members = []
    if ticket.project_id:
        # Get project's team_id
        project_stmt = sa.text("SELECT team_id FROM project WHERE id = :project_id")
        project_result = db.session.execute(project_stmt, {"project_id": ticket.project_id}).fetchone()
        if project_result and project_result.team_id:
            team_members = User.query.filter_by(team_id=project_result.team_id, approved=True).all()
    
    # If no team members found or user is admin, show appropriate options
    if current_user.role == 'admin':
        # Admin can assign to anyone
        team_members = User.query.filter_by(approved=True).all()
    elif current_user.role == 'manager' and not team_members:
        # Manager can assign to members of their team if no project team members found
        team_members = User.query.filter_by(team_id=current_user.team_id, approved=True).all()
    
    return render_template('reassign_ticket.html', ticket=ticket, team_members=team_members)

@app.route('/api/people', methods=['GET', 'POST'])
def api_people():
    from models import User
    if request.method == 'GET':
        users = User.query.filter_by(approved=True).all()
        people = []
        for user in users:
            people.append({
                "name": user.name,
                "role": user.role
            })
        return jsonify(people)
    elif request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        # Create new user with default role and pending approval
        new_user = User(
            name=email.split('@')[0].capitalize(),
            email=email,
            role='visitor',
            approved=False,
            password=''  # No password set yet
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"status": "success", "person": {"name": new_user.name, "role": new_user.role}}), 201

@app.route('/api/teams', methods=['GET', 'POST'])
def api_teams():
    from models import Team, User
    if request.method == 'GET':
        teams = Team.query.all()
        teams_list = []
        for team in teams:
            members = User.query.filter_by(team_id=team.id, approved=True).all()
            members_list = []
            for m in members:
                members_list.append({
                    "name": m.name,
                    "role": m.role
                })
            teams_list.append({
                "name": team.name,
                "project": team.project if hasattr(team, 'project') else '',
                "members": members_list
            })
        return jsonify(teams_list)
    elif request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        project = data.get('project')
        member_emails = data.get('members')
        members = []
        for email in member_emails:
            user = User.query.filter_by(email=email).first()
            if user:
                members.append(user)
        new_team = Team(name=name, project=project)
        db.session.add(new_team)
        db.session.commit()
        # Assign members to the new team
        for member in members:
            member.team_id = new_team.id
        db.session.commit()
        return jsonify({"status": "created", "team": {"name": new_team.name, "project": new_team.project, "members": member_emails}})

@app.route('/api/team/<int:team_id>/members')
@login_required
def api_team_members(team_id):
    from models import Team, User
    
    # Only admin can access this endpoint
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    team = Team.query.get_or_404(team_id)
    members = User.query.filter_by(team_id=team_id, approved=True).all()
    
    members_list = []
    for member in members:
        members_list.append({
            "id": member.id,
            "name": member.name,
            "role": member.role,
            "is_manager": member.id == team.manager_id
        })
    
    return jsonify(members_list)

@app.route('/team/<int:team_id>/update_manager', methods=['POST'])
@login_required
def update_team_manager(team_id):
    from models import Team, User
    
    # Only admin can update team manager
    if current_user.role != 'admin':
        abort(403)
    
    team = Team.query.get_or_404(team_id)
    manager_id = request.form.get('manager_id')
    
    if not manager_id:
        flash('No team member selected')
        return redirect(url_for('teams_page'))
    
    # Verify the user is part of the team
    user = User.query.get(int(manager_id))
    if not user or user.team_id != team_id:
        flash('Invalid team member selected')
        return redirect(url_for('teams_page'))
    
    # Update the user's role to manager if not already
    if user.role != 'manager':
        user.role = 'manager'
    
    # Update the team's manager
    team.manager_id = user.id
    db.session.commit()
    
    # Create notification for the new team lead
    create_notification(
        user_id=user.id,
        message=f'You have been assigned as Team Lead for {team.name}',
        link=url_for('teams_page')
    )
    
    # Notify team members about the new lead
    team_members = User.query.filter_by(team_id=team_id, approved=True).all()
    for member in team_members:
        if member.id != user.id:  # Don't notify the lead themselves
            create_notification(
                user_id=member.id,
                message=f'{user.name} is now the Team Lead for {team.name}',
                link=url_for('teams_page')
            )
    
    flash(f'{user.name} has been set as the Team Lead for {team.name}')
    return redirect(url_for('teams_page'))

@app.route('/api/timeline')
def api_timeline():
    from models import Project
    projects = Project.query.all()
    projects_list = []
    for project in projects:
        projects_list.append({
            "id": project.id,
            "name": project.name,
            "start_date": project.start_date.strftime('%Y-%m-%d') if project.start_date else '',
            "deadline": project.deadline.strftime('%Y-%m-%d') if project.deadline else '',
            "status": project.status
        })
    return jsonify(projects_list)

@app.errorhandler(Exception)
def handle_exception(e):
    return f"<pre>{e}</pre>", 500

@app.route('/create_project', methods=['GET', 'POST'])
@login_required
def create_project():
    from models import Project, User, Team
    
    # Only admin and manager can create projects
    if current_user.role not in ['admin', 'manager']:
        abort(403)
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        team_lead_id = request.form.get('team_lead')
        team_id = request.form.get('team_id')
        start_date = request.form.get('start_date')
        deadline = request.form.get('deadline')
        status = request.form.get('status', 'Active')
        
        if not (name and team_lead_id and team_id and start_date and deadline):
            flash('Please fill in all required fields.')
            return redirect(url_for('create_project'))
            
        # Validate team_id
        team = Team.query.get(int(team_id))
        if not team:
            flash('Selected team does not exist.')
            return redirect(url_for('create_project'))
        
        # Check for existing project with same name
        from datetime import datetime
        existing_project = Project.query.filter_by(name=name).first()
        if existing_project:
            flash('Project with this name already exists.')
            return redirect(url_for('create_project'))
        
        # Create new project
        new_project = Project(
            name=name,
            description=description,
            team_lead_id=int(team_lead_id),
            start_date=datetime.strptime(start_date, '%Y-%m-%d').date(),
            deadline=datetime.strptime(deadline, '%Y-%m-%d').date(),
            status=status,
            team_id=int(team_id)
        )
        
        db.session.add(new_project)
        db.session.commit()
        flash('Project created successfully!')
        return redirect(url_for('projects_page'))
    
    # Get all teams and team leads for dropdowns
    teams = Team.query.all()
    team_leads = User.query.filter_by(role='manager', approved=True).all()
    
    return render_template('create_project.html', team_leads=team_leads, teams=teams)

@app.route('/project/<int:project_id>/board')
@login_required
def project_board(project_id):
    from models import Project, Ticket
    import sqlalchemy as sa
    
    project = Project.query.get_or_404(project_id)
    
    # Use a raw SQL query to avoid the parent_id column
    try:
        # Try to get project tickets with parent_id column
        project_tickets = Ticket.query.filter_by(project_id=project_id).all()
    except Exception as e:
        # If parent_id column doesn't exist, use a custom query
        stmt = sa.text("SELECT id, title, description, type, priority, assignee, status, public, project_id, start_date, end_date FROM ticket WHERE project_id = :project_id")
        result = db.session.execute(stmt, {"project_id": project_id})
        project_tickets = []
        for row in result:
            ticket = Ticket(
                id=row.id,
                title=row.title,
                description=row.description,
                type=row.type,
                priority=row.priority,
                assignee=row.assignee,
                status=row.status,
                public=row.public,
                project_id=row.project_id,
                start_date=row.start_date,
                end_date=row.end_date
            )
            project_tickets.append(ticket)
    
    # Filter tickets based on user role
    visible_tickets = []
    if current_user.role == 'admin':
        # Admin can see all tickets
        visible_tickets = project_tickets
    elif current_user.role == 'manager':
        # Manager can see all tickets in their projects
        visible_tickets = project_tickets
    else:
        # Developers can only see their own tickets and public tickets
        for ticket in project_tickets:
            if ticket.assignee == current_user.name:  # Their own tickets
                visible_tickets.append(ticket)
            elif ticket.public:  # Public tickets in the project
                visible_tickets.append(ticket)
    
    tickets = {'To Do': [], 'In Progress': [], 'In Review': [], 'Done': []}
    for ticket in visible_tickets:
        tickets.setdefault(ticket.status, []).append(ticket)
    return render_template('board.html', tickets=tickets, project=project)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from models import User, Team
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            from werkzeug.security import generate_password_hash
            admin_user = User(
                name='Default Admin',
                email='admin@example.com',
                password=generate_password_hash('adminpassword'),
                role='admin',
                approved=True
            )
            db.session.add(admin_user)
            db.session.commit()
        # Initialize default teams alpha, beta, gamma with managers
        default_teams = ['alpha', 'beta', 'gamma']
        for team_name in default_teams:
            team = Team.query.filter_by(name=team_name).first()
            if not team:
                # Assign manager for each team (for now assign admin as manager)
                team = Team(name=team_name, manager_id=admin_user.id)
                db.session.add(team)
        db.session.commit()
        # Ensure teams are visible on teams.html by querying them
        teams = Team.query.all()
        print(f"Teams in DB: {[team.name for team in teams]}")
    app.run(debug=True)