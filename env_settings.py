import os
import dotenv

dotenv.load_dotenv('.env')

#db_access
db_host = os.environ['host']
db_port = os.environ['port']
db_name = os.environ['dbname']
db_user = os.environ['user']
db_password = os.environ['password']

#api_access
login = os.environ['login']
api_key = os.environ['api_key']