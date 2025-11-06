from flask import Blueprint

staffing_bp = Blueprint(
    'staffing', 
    __name__,
    url_prefix='/staffing',
    template_folder='templates',
    static_folder='static',
    static_url_path='/staffing/static'
)

