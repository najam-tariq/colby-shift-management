from flask import Blueprint

staffing_bp = Blueprint('staffing', __name__,
                       template_folder='templates',
                       static_folder='static',
                       url_prefix='/staffing',
                       static_url_path='/static')

from . import routes
