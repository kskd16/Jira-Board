from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Team

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            if not user.approved:
                flash('Your account is pending approval by admin.')
                return redirect(url_for('auth.login'))
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        
        # Check if user with this email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('A user with this email already exists. Please use a different email.')
            return redirect(url_for('auth.register'))
        
        hashed_pw = generate_password_hash(request.form['password'])
        role = request.form['role'].lower()  # Convert role to lowercase
        team = None
        
        # Only assign team if not a visitor or if team is selected
        team_name = request.form.get('team')
        if team_name and role != 'visitor':
            team = Team.query.filter_by(name=team_name).first()
        
        try:
            # Print debug information
            print(f"Registering new user: {request.form['name']}, Email: {email}, Role: {role}")
            
            new_user = User(
                name=request.form['name'],
                email=email,
                password=hashed_pw,
                role=role,
                team=team,
                approved=False  # All users need approval
            )
            db.session.add(new_user)
            db.session.commit()
            
            # Print confirmation
            print(f"User created with ID: {new_user.id}, Role: {new_user.role}, Approved: {new_user.approved}")
            
            flash('Account created! Please wait for admin approval.')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {str(e)}')
            return redirect(url_for('auth.register'))
    
    # Get all teams for the dropdown
    teams = Team.query.all()
    return render_template('register.html', teams=teams)

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
