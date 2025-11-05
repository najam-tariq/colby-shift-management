from flask import Blueprint

scheduler_bp = Blueprint(
    'scheduler', 
    __name__,
    url_prefix='/scheduler',
    template_folder='templates',
    static_folder='static',
    static_url_path='/scheduler/static'
)

from . import routes

