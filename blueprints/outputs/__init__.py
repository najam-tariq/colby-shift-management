from flask import Blueprint

outputs_bp = Blueprint(
    'outputs', 
    __name__,
    url_prefix='/outputs',
    template_folder='templates',
    static_folder='static',
    static_url_path='/outputs/static'
)

from . import routes

