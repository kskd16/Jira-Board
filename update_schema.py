"""
This script adds the parent_id column to the ticket table in the database.
Run this script once to update the database schema.
"""
from app import app, db
import sqlalchemy as sa

def add_parent_id_column():
    with app.app_context():
        try:
            # Check if column exists
            db.session.execute(sa.text("SELECT parent_id FROM ticket LIMIT 1"))
            print("Column parent_id already exists.")
        except Exception as e:
            print(f"Column does not exist: {e}")
            try:
                # Add the column
                db.session.execute(sa.text("ALTER TABLE ticket ADD COLUMN parent_id INTEGER REFERENCES ticket(id)"))
                db.session.commit()
                print("Column parent_id added successfully.")
                
                # Update models.py to reflect the change
                print("\nIMPORTANT: The database schema has been updated.")
                print("You need to restart the application for the changes to take effect.")
                print("After restarting, the Epic-Feature-Story hierarchy will be available.")
            except Exception as e:
                print(f"Error adding column: {e}")
                db.session.rollback()
                print("\nTroubleshooting tips:")
                print("1. Make sure the application is not running when updating the schema")
                print("2. Check if you have write permissions to the database file")
                print("3. Try running the script with administrator privileges")

if __name__ == "__main__":
    add_parent_id_column()