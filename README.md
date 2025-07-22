# Jira Clone - Setup Instructions

## Database Schema Update
Before running the application, you need to update the database schema to support the full Epic-Feature-Story hierarchy functionality:

1. Run the schema update script:
   ```
   python update_schema.py
   ```

2. Start the application:
   ```
   python app.py
   ```

## Ticket Hierarchy
The application supports a three-level hierarchy of work items:

1. **Epics** (Top Level)
   - Large bodies of work that can be broken down into features
   - Example: "User Authentication System"

2. **Features** (Mid Level)
   - Specific functionality that belongs to an epic
   - Example: "Password Reset Functionality"

3. **Stories/Tasks/Bugs** (Bottom Level)
   - Smallest units of work that belong to features
   - Examples: "Create Password Reset Email Template" (Story), "Fix Login Button" (Bug)

Without running the schema update, you can still view a simplified hierarchy visualization on the Hierarchy page, but the relationships between tickets won't be stored in the database.

## Features
- Epic-Feature-Story hierarchy for better work organization
- Drag and drop Kanban board
- Role-based access control
- Team management
- Project tracking
- Dashboard with summary statistics
- Advanced filtering and search

## Default Login
- Email: admin@example.com
- Password: adminpassword