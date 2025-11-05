from flask import Blueprint

availability_bp = Blueprint(
    'availability', 
    __name__,
    url_prefix='/availability',
    template_folder='templates',
    static_folder='static',
    static_url_path='/availability/static'
)

from . import routes

