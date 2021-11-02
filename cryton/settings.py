import os
from cryton.etc import config

TIME_ZONE = config.TIME_ZONE
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = '-g)+plkhyjj2veze+!@rpmbo^0ugn_gx6@dt_looylp839bl+5'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'cryton.cryton_rest_api',
    'drf_yasg',
    'django_filters',
    'corsheaders'
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

CORS_ORIGIN_ALLOW_ALL = True

DEBUG = True if 'debug' == os.getenv('CRYTON_LOGGER', 'debug') else False

ALLOWED_HOSTS = "*"

# Change to True for CI/CD testing environment
DOCKER = False

if DOCKER:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'cryton',
            'USER': 'cryton',
            'PASSWORD': 'cryton',
            'HOST': 'postgres',
            'PORT': 5432,
        }
    }
else:

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config.DB_NAME,
            'USER': config.DB_USERNAME,
            'PASSWORD': config.DB_PASSWORD,
            'HOST': config.DB_HOST
        }
    }

ROOT_URLCONF = 'cryton.urls'

STATIC_URL = '/static/'
STATIC_ROOT = '/usr/local/apache2/web/static/'

# OIDC Authentication

AUTHENTICATED_REST_API = False

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
}

if AUTHENTICATED_REST_API:
    REST_FRAMEWORK.update({
        'DEFAULT_PERMISSION_CLASSES': (
            'rest_framework.permissions.IsAuthenticated',
        ),
        'DEFAULT_AUTHENTICATION_CLASSES': (
            # 'oidc_auth.authentication.JSONWebTokenAuthentication',
            'oidc_auth.authentication.BearerTokenAuthentication',
        ),
    })

    OIDC_AUTH = {
        # Specify OpenID Connect endpoint. Configuration will be
        # automatically done based on the discovery document found
        # at <endpoint>/.well-known/openid-configuration
        'OIDC_ENDPOINT': 'https://YOUR-OIDC-PROVIDER',

        # Accepted audiences the ID Tokens can be issued to
        # TODO change
        'OIDC_AUDIENCES': ('YOUR-OIDC-AUDIENCE',),

        # (Optional) Function that resolves id_token into user.
        # This function receives a request and an id_token dict and expects to
        # return a User object. The default implementation tries to find the user
        # based on username (natural key) taken from the 'sub'-claim of the
        # id_token.
        'OIDC_RESOLVE_USER_FUNCTION': 'oidc_auth.authentication.get_user_by_id',

        # (Optional) Number of seconds in the past valid tokens can be
        # issued (default 600)
        'OIDC_LEEWAY': 600,

        # (Optional) Time before signing keys will be refreshed (default 24 hrs)
        'OIDC_JWKS_EXPIRATION_TIME': 24 * 60 * 60,

        # (Optional) Time before bearer token validity is verified again (default 10 minutes)
        'OIDC_BEARER_TOKEN_EXPIRATION_TIME': 10 * 60,

        # (Optional) Token prefix in JWT authorization header (default 'JWT')
        # 'JWT_AUTH_HEADER_PREFIX': 'JWT',

        # (Optional) Token prefix in Bearer authorization header (default 'Bearer')
        'BEARER_AUTH_HEADER_PREFIX': 'Bearer',
    }

SWAGGER_SETTINGS = {
    'DEFAULT_MODEL_RENDERING': 'example'
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 1000000000
USE_TZ = True
