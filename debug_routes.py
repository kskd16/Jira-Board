@app.route('/debug/users')
@login_required
def debug_users():
    from models import User
    
    # Only admin can access this debug route
    if current_user.role != 'admin':
        abort(403)
    
    all_users = User.query.all()
    
    return render_template('debug_users.html', users=all_users)