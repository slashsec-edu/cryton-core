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
![Coverage](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-core/badges/master/coverage.svg)
# Name
**Cryton** - Breach Emulation & Attack Simulation Toolset

# Description
Cryton is a set of tools for complex attack scenarios automation. Through usage of core and attack modules it provides ways 
to plan, execute and evaluate multi step attacks.

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
Cryton uses **PostgreSQL** as it's internal database, so this must be installed and started on your system. So far the only 
supported OS is **Kali Linux**, preferably 2019.1 stable release. Additionally there are some other dependencies. Please 
check you have following tools/packages installed:
* python3.7
* (optional) pipenv
* postgresql
* libpq5
* libpq-dev

# Installation

Important note: this guide only explains how to install **Cryton Core** package. For being able to execute the attack 
scenarios, you also need to install the **Cryton Worker** package. If you want to use attack modules provided by Cryton, 
you have to also install **Cryton Modules**.

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

**The following steps are ment for production configuration, which is set by default!**

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

Everything should be set. Check if the installation was successful by either installing Cryton CLI or testing REST API with curl:

~~~~
user@localhost:~ /cryton-core $ curl localhost:8000
{"runs":"http://localhost:8000/cryton/api/v1/runs/","plans":"http://localhost:8000/cryton/api/v1/plans/",
"plan_executions":"http://localhost:8000/cryton/api/v1/plan_executions/","stages":"http://localhost:8000/cryton/api/v1/stages/",
"stage_executions":"http://localhost:8000/cryton/api/v1/stage_executions/","steps":"http://localhost:8000/cryton/api/v1/steps/",
"step_executions":"http://localhost:8000/cryton/api/v1/step_executions/","workers":"http://localhost:8000/cryton/api/v1/workers/"}
~~~~

### Development
For development environment, there is a light version of the production Docker which can be used with a debugger.

First update your `.env` file with:  

- `CRYTON_DB_HOST=cryton_db`
- `CRYTON_LOGGER=debug`

When managing docker for development we must provide its docker-compose file: `docker-compose -f docker-compose.dev.yml`.

To **deploy** use:
~~~~
docker-compose -f docker-compose.dev.yml up -d
~~~~

To be able to use *cryton-manage* command run:

~~~~
docker-compose exec cryton_app python setup.py egg_info
~~~~

After that run **database migrations**:

~~~~
docker-compose exec cryton_app cryton-manage migrate
~~~~

#### Additional steps for setting up PyCharm debugger

**cryton_app configuration**  
This configuration will allow us to debug code which will be executed by requests from the REST API. 
Code is automatically reloaded on change.  

First we need to set up interpreter. Go to *File* -> *Settings* -> *Project: cryton-core* -> *Python Interpreter* -> 
click the settings icon -> click the *add...* button -> select *Docker Compose*.
1. **Server** - Configure docker server if you haven't done it already (Usually there is no need to do anything. 
Simply click on *New...* and then on *OK*. That should be enough.)
2. **Configuration files** - Choose `docker-compose.dev.yml`.
3. **Service** - Select `cryton_app`
4. **Python interpreter path** - `python`

Now we can create a **run configuration**:  
Select *Django Server* template and fill it with the following values:
- **Name**: `cryton-app`
- **Host**: `0.0.0.0`
- **Port**: `8000`
- **Environment variables**: `PYTHONUNBUFFERED=1;DJANGO_SETTINGS_MODULE=cryton.settings`
- **Python interpreter**: The one we just created (*Docker Compose cryton_app*).


**cryton_listener configuration**  
This configuration will allow us to debug code which will be executed through the listener.
Code must be reloaded manually using *Rerun 'cryton-listener'* button or *Ctrl+F5*.  

First we need to set up interpreter. (**Same as for *cryton_app*, however use cryton_listener as a service**)

Now we can create a **run configuration**:  
Select *Python* template and fill it with the following values:
- **Name**: `cryton-listener`
- **Script path**: `/path/to/cryton-core/cryton/manage.py`
- **Parameters**: `startlistener`
- **Environment variables**: `PYTHONUNBUFFERED=1;DJANGO_SETTINGS_MODULE=cryton.settings`
- **Python interpreter**: The one we just created (*Docker Compose cryton_listener*).
- **Working directory**: `/path/to/cryton-core/cryton` (should be set automatically)


**Reverting the cryton_app service to its original state**  
If you already used the *cryton-app* configuration or ran some tests using PyCharm you will find that running tests through 
command line or possibly other features are unavailable. To restore the `cryton_app` service to its original state use: 

~~~~
docker-compose -f docker-compose.dev.yml up -d cryton_app
~~~~

## From source (manual; not recommended)

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
