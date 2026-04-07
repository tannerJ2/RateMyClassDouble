'''

this is the file you run to actually start your web application. 
Think of it as the on/off switch

'''


from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    db.create_all()  # remove this line after running once

if __name__ == '__main__':
    app.run(debug=True)
 