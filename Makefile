.PHONY: install setup run test check demo
# Сначала активируйте venv: команды используют python из текущего PATH.
install:
	python -m pip install -r requirements.txt
setup: install
	python manage.py migrate
	python manage.py seed_demo
run:
	python manage.py runserver 127.0.0.1:8000
test:
	python manage.py test
check:
	python manage.py check
	python manage.py makemigrations --check --dry-run
demo:
	python manage.py seed_demo
