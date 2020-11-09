<!-- TOC depthFrom:1 depthTo:6 withLinks:1 updateOnSave:1 orderedList:0 -->

- [Name](#name)
- [Description](#description)
- [Dependencies](#dependencies)
- [Installation](#installation)
	- [From source](#from-source)
- [Usage](#usage)
	- [CLI](#cli)
	- [Shell](#shell)

<!-- /TOC -->
![Coverage](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-oop/badges/master/coverage.svg)
# Name
**Cryton** - Breach Emulation & Attack Simulation Toolset

# Description
Cryton is a set of tools for complex attack scenarios automation. Through usage of core and attack modules it provides ways to plan, execute and evaluate multi step attacks.

There are 4 separate projects of Cryton toolset:
* **Cryton Core**: Contains Cryton Core functions for working with database, task scheduler and execution mechanism.
* **Cryton Worker**: Contains functions to execute attack modules both locally and remotely.
* **Cryton Modules**: Contains attack modules that can be executed via Worker.
* **Cryton CLI**: Command Line Interface for working with Cryton. It uses REST API, which is part of *Cryton Core*.

Cryton is tested and runs best under Kali Linux OS 2019.1 using *root* user.

# Dependencies

## For docker
* docker.io
* docker-compose

## For manual installation
Cryton uses **PostgreSQL** as it's internal database, so this must be installed and started on your system. So far the only supported OS is **Kali Linux**, preferably 2019.1 stable release. Additionally there are some other dependencies. Please check you have following tools/packages installed:
* python3.7
* (optional) pipenv
* postgresql
* libpq5
* libpq-dev

# Installation

Important note: this guide only explains how to install **Cryton Core** package. For being able to execute the attack scenarios, you also need to install the **Cryton Worker** package. If you want to use attack modules provided by Cryton, you have to also install **Cryton Modules**.

## Docker (recommended)

First make sure you have Docker installed:

~~~~
user@localhost:~ $ sudo apt install docker.io docker-compose
~~~~ 

Add yourself to the group docker so you can work with docker CLI without sudo:

~~~~
user@localhost:~ $ sudo groupadd docker
user@localhost:~ $ sudo usermod -aG docker $USER
user@localhost:~ $ newgrp docker 
user@localhost:~ $ docker run hello-world
~~~~

Now, run docker-compose, which will pull, build and start all necessary docker images:
~~~~
user@localhost:~ $ cd cryton-core/
user@localhost:~ /cryton-core $ docker-compose up -d
~~~~

This process might take a while, especially if it is the first time you run it - Cryton image must be built.
After a while you should see something like this:
~~~~
Creating db     ... done
Creating rabbit ... done
Creating scheduler ... done
Creating listener  ... done
Creating app       ... done
~~~~

After that, you should run database migrations:

~~~~
user@localhost:~ /cryton-core $ docker-compose exec cryton_app cryton-manage makemigrations cryton_rest_api
user@localhost:~ /cryton-core $ docker-compose exec cryton_app cryton-manage migrate
~~~~

Everything should be set. Check if the installation was successful by either installing Cryton CLI or testing REST API with curl:

~~~~
user@localhost:~ /cryton-core $ curl localhost:8000
{"runs":"http://localhost:8000/cryton/api/v1/runs/","plans":"http://localhost:8000/cryton/api/v1/plans/","plan_executions":"http://localhost:8000/cryton/api/v1/plan_executions/","stages":"http://localhost:8000/cryton/api/v1/stages/","stage_executions":"http://localhost:8000/cryton/api/v1/stage_executions/","steps":"http://localhost:8000/cryton/api/v1/steps/","step_executions":"http://localhost:8000/cryton/api/v1/step_executions/","workers":"http://localhost:8000/cryton/api/v1/workers/"}
~~~~


### Production
For production environment, there are some other options needed (such as publishing ports to public IP addressuse, persistent database data volume etc. For production deployment, use:
~~~~
user@localhost:~ /cryton-core $ docker-compose -f docker-compose.prod.yml up -d
~~~~ 
The rest of the steps is the same as above.

## From source (manual)

First you need to create database and database tables Cryton internal storage. This database is also used for scheduler and tasks persistence:
~~~~
user@localhost:~ $ sudo su postgres
postgres@localhost:~ $ psql -c "CREATE DATABASE cryton;"
postgres@localhost:~ $ psql -c "CREATE USER cryton WITH PASSWORD 'cryton';GRANT ALL PRIVILEGES ON DATABASE cryton TO cryton;ALTER DATABASE cryton OWNER TO cryton; ALTER USER cryton CREATEDB;";
postgres@localhost:~ $ exit
~~~~

## From source

Please clone respective git repositories and install them using setuptools. You can use pipenv for creating virtual environment.


First, obtain the source:

```
root@localhost:~ $ git clone <cryton-repo>; cd cryton-oop
```

Then create the virtual environment using Pipenv:

```
root@localhost:~/cryton-oop$ pipenv shell # has to be virtual environment with python3.7
```

Use setup.py to install the package:
```
(cryton-oop) root@localhost:~/cryton-oop$ python setup.py install
```

Edit the configuration files in /etc/cryton according to your preferences.

Also, if you are not running Cryton in Docker environment, you have to change the default hostname of machine where the database is running. In this case, when installing locally, you should change it to 'localhost' in /etc/cryton/config.ini:
~~~~
[CRYTON]
DB_NAME: cryton
DB_USERNAME: cryton
DB_PASSWORD: cryton
DB_HOST: db <---- Change this to 'localhost'
~~~~

This also applies to Scheduler service, which will run on localhost as well. This option is also in /etc/cryton/config.ini:

~~~~
[SCHEDULER]
LHOSTNAME=scheduler <---- Change this to 'localhost'
LPORT=12345
USE_PROCESS_POOL: False
MISFIRE_GRACE_TIME: 60
~~~~

After successful installation the only thing needed is Django _migration_ for creating default tables in Cryton database:

```
(cryton-oop) user@localhost:~/cryton-oop$ cryton-manage makemigrations cryton_rest_api
(cryton-oop) user@localhost:~/cryton-oop$ cryton-manage migrate
```
To check if installation was successfull try to start the REST API:

~~~~

(cryton-oop) root@kali:/opt/cryton$ cryton-manage runserver
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
May 25, 2020 - 06:38:32
Django version 3.0.5, using settings 'cryton.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CONTROL-C.

~~~~

# Usage

Every Cryton plan run can be described by simple formula:
~~~~
Plan Template + Variables = Plan Instance
Plan Instance + Workers = Plan Run
~~~~

## 1. Choose or Design a Plan Template

Choose one of the YAML Plan Templates or design your own.

## 2. Create a Plan Instance

Plan Templates can utilize a number of variables that need to be provided during Instantiation process. Do this by specifying a Variables file.

## 3. Create a Run

Create a Run by choosing Plan Instance and providing list of Workers for execution.

## 4. Schedule or Execute a Run

You can either Schedule the Run for specific date/time, or execute it directly. Run will then be executed on every Worker simultaneously.

## 5. Read the Report

Anytime during running of cryton the output file can be generated, which also complies to YAML format, and it contains list of Stages/Steps, their success and output or, if available, error message.

### Complete Execution

There are 3 actions you need to do to execute your plan:
* **Create** the Run
* **Start** scheduler service
* **Start** Worker
* **Run** the plan

First step (or steps) is described in sections above.

Second step is running the Worker service. Do not forget to run this inside _separate pipenv_:

~~~~
(cryton-worker) user@localhost:/opt/cryton-worker$ cryton-worker
Starting server. Listening on 127.0.0.1:50666
~~~~

Third step is starting the scheduler service. Scheduler will now listen on a local TCP port for RPC connections from Cryton Core:

~~~~
(cryton) user@localhost:/opt/cryton$ cryton-manage startscheduler
Starting scheduler service. Listening on 127.0.0.1:12345
~~~~

Last step is running the plan. For that you need **Cryton CLI**. Follow instructions in its README file: https://gitlab.ics.muni.cz/cryton/cryton-cli
