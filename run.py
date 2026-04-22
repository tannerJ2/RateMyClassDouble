'''

this is the file you run to actually start your web application. 
Think of it as the on/off switch

'''

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
 