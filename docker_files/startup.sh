#!/bin/sh

cryton-manage migrate &&
gunicorn cryton.wsgi --bind 0.0.0.0:8000
