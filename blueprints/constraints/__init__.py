from flask import Blueprint

constraints_bp = Blueprint(
    'constraints', 
    __name__,
    url_prefix='/constraints',
    template_folder='templates',
    static_folder='static',
    static_url_path='/constraints/static'
)

from . import routes

