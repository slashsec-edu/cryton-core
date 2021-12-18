[[_TOC_]]

![Coverage](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-core/badges/master/coverage.svg)

# Cryton Core

## Description
Cryton Core is the center point of Cryton toolset. It is used for:
- Creating, planning, and scheduling attack scenarios.
- Generating reports from attack scenarios.
- Controlling Workers and scenarios execution.

## About Cryton
It is a breach Emulation & Attack Simulation Toolset.
It is a set of tools for complex attack scenarios' automation. Through usage of core and attack modules it provides ways 
to plan, execute and evaluate multistep attacks.

There are 4 main separate projects of Cryton toolset:
- **Cryton Core**: Contains Cryton Core functionality for working with database, task scheduler and execution mechanisms.
- **Cryton Worker**: Contains functionality to execute attack modules both locally and remotely.
- **Cryton Modules**: Contains attack modules that can be executed via Worker.
- **Cryton CLI**: Command Line Interface for working with Cryton. It uses REST API, which is part of *Cryton Core*.

[Link to the documentation](https://beast-public.gitlab-pages.ics.muni.cz/cryton/cryton-documentation/).

## Installation
Important note: this guide only explains how to install the **Cryton Core** package. To be able to execute the attack 
scenarios, you also need to install the **[Cryton Worker](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-worker)** 
and **[Cryton CLI](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-cli)** package. Optionally you can also install
[Cryton Frontend](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-frontend) for non-command line experience.

### Using Docker Compose - for production (recommended)

**Dependencies**
- docker.io
- docker-compose

First make sure you have installed dependencies:
```
sudo apt install docker.io docker-compose
``` 

Add yourself to the group *docker*, so you can work with Docker CLI without sudo:
```
sudo groupadd docker
sudo usermod -aG docker $USER
newgrp docker 
docker run hello-world
```

For correct installation you need to update `.env` file. For example, you should change default credentials. For more 
information about *Cryton Worker* settings go to the [settings section](#settings).

**!The following steps are ment for production configuration, which is set by default!**

Now, run docker-compose, which will pull, build and start all necessary docker images:
```
cd cryton-core/
docker-compose up -d
```

This process might take a while, especially if it is the first time you run it - images must be built.
After a while you should see something like this:
```
Creating cryton_db         ... done
Creating cryton_pgbouncer  ... done
Creating cryton_rabbit     ... done
Creating cryton_apache     ... done
Creating cryton_listener   ... done
Creating cryton_app        ... done
```

Everything should be set. Check if the installation was successful by either installing Cryton CLI or testing REST API 
with curl:
```
curl localhost:8000
```

Expected result:
```
{"runs":"http://localhost:8000/cryton/api/v1/runs/","plans":"http://localhost:8000/cryton/api/v1/plans/",
"plan_executions":"http://localhost:8000/cryton/api/v1/plan_executions/","stages":"http://localhost:8000/cryton/api/v1/stages/",
"stage_executions":"http://localhost:8000/cryton/api/v1/stage_executions/","steps":"http://localhost:8000/cryton/api/v1/steps/",
"step_executions":"http://localhost:8000/cryton/api/v1/step_executions/","workers":"http://localhost:8000/cryton/api/v1/workers/"}
```


### Using Docker Compose - for development
For development environment, there is a light version of the production Docker which can be used with a debugger.

First update your `.env` file with:  

- `CRYTON_DB_HOST=cryton_db`
- `CRYTON_LOGGER=debug`

When managing docker for development we must provide its docker-compose file: `docker-compose -f docker-compose.dev.yml`.

To **deploy** use:
```
docker-compose -f docker-compose.dev.yml up -d
```

To be able to use *cryton-manage* command run:

```
docker-compose exec cryton_app python setup.py egg_info
```

After that run **database migrations**:

```
docker-compose exec cryton_app cryton-manage migrate
```

#### Additional steps for setting up PyCharm debugger

##### cryton_app configuration  
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


##### cryton_listener configuration  
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


##### Reverting the cryton_app service to its original state  
If you already used the *cryton-app* configuration or ran some tests using PyCharm you will find that running tests through 
command line or possibly other features are unavailable. To restore the `cryton_app` service to its original state use: 

```
docker-compose -f docker-compose.dev.yml up -d cryton_app
```

Optionally restart the whole docker-compose using:

```
docker-compose -f docker-compose.dev.yml restart
```

### Using virtual environment (NOT RECOMMENDED)
It is possible to install Cryton Core without using docker, however it isn't supported since it takes many steps. If you 
still want to do it, you will have to reverse engineer the docker-compose file or create a ticket, if you want us to 
support this type of installation.

## Settings
Cryton Core uses environment variables for its settings. Please update variables for your use case.
```
CRYTON_RABBIT_USERNAME=admin
CRYTON_RABBIT_PASSWORD=mypass
CRYTON_RABBIT_SRV_ADDR=cryton_rabbit
CRYTON_RABBIT_SRV_PORT=5672
CRYTON_DB_NAME=cryton
CRYTON_DB_USERNAME=cryton
CRYTON_DB_PASSWORD=cryton
CRYTON_DB_HOST=cryton_pgbouncer
Q_ATTACK_RESPONSE_NAME=cryton_core.attack.response
Q_AGENT_RESPONSE_NAME=cryton_core.agent.response
Q_CONTROL_RESPONSE_NAME=cryton_core.control.response
Q_EVENT_RESPONSE_NAME=cryton_core.event.response
Q_CONTROL_REQUEST_NAME=cryton_core.control.request
CRYTON_LOGGER=prod
CRYTON_PUBLIC_PORT=8000
CRYTON_TZ=UTC
CRYTON_RPC_TIMEOUT=1200

```

To update environment variable, update the `.env` file in the *cryton-core* directory **before starting the docker image**.

Settings description: 
- `CRYTON_RABBIT_USERNAME` - (**string**) RabbitMQ's username used for connection
- `CRYTON_RABBIT_PASSWORD` - (**string**) RabbitMQ's password used for connection
- `CRYTON_RABBIT_SRV_ADDR` - (**string**) RabbitMQ's address used for connection (**do not change, if you don't know what you're doing**)
- `CRYTON_RABBIT_SRV_PORT` - (**int**) RabbitMQ's port used for connection (**do not change, if you don't know what you're doing**)
- `CRYTON_DB_NAME` - (**string**) Database name used for connection (**do not change, if you don't know what you're doing**)
- `CRYTON_DB_USERNAME` - (**string**) Database username used for connection
- `CRYTON_DB_PASSWORD` - (**string**) Database password used for connection
- `CRYTON_DB_HOST` - (**int**) Database host used for connection (**do not change, if you don't know what you're doing**)
- `Q_ATTACK_RESPONSE_NAME` - (**string**) Rabbit queue where responses from attack modules should return 
(**do not change, if you don't know what you're doing**)
- `Q_AGENT_RESPONSE_NAME` - (**string**) Rabbit queue where responses from agent control requests should return 
(**do not change, if you don't know what you're doing**)
- `Q_CONTROL_RESPONSE_NAME` - (**string**) Rabbit queue where responses from Worker control requests should return 
(**do not change, if you don't know what you're doing**)
- `Q_EVENT_RESPONSE_NAME` - (**string**) Rabbit queue where responses from events should return 
(**do not change, if you don't know what you're doing**)
- `Q_CONTROL_REQUEST_NAME` - (**string**) Rabbit queue where control requests should be sent 
(**do not change, if you don't know what you're doing**)
- `CRYTON_LOGGER` - (**string**) What logger should be used (prod - only info logs and higher/debug - any logs)
- `CRYTON_PUBLIC_PORT` - (**int**) (**do not change, if you don't know what you're doing**)
- `CRYTON_TZ` - (**string**) Internally used timezone (**do not change, if you don't know what you're doing**)
- `CRYTON_RPC_TIMEOUT` - (**int**) Timeout for RabbitMQ RPC requests (**do not change, if you don't know what you're doing**)

## Usage
In order to be able to control Cryton Core, you have to send requests to its REST API. This can be done manually, or via 
[Cryton CLI](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-cli) or 
[Cryton Frontend](https://gitlab.ics.muni.cz/beast-public/cryton/cryton-frontend).

### REST API
REST API is the only way to communicate with Cryton Core. It is by default running at 
[http://0.0.0.0:8000](http://0.0.0.0:8000). And its interactive documentation can be found at 
[http://0.0.0.0:8000/doc](http://0.0.0.0:8000/doc).

### Execution example
Every Cryton plan run can be described by simple formula:
```
Plan Template + Variables = Plan Instance
Plan Instance + Workers = Plan Run
```

**1. Choose or Design a Plan Template**  
Choose one of the YAML Plan Templates or design your own.

**2. Create a Plan Instance**  
Plan Templates can utilize a number of variables that need to be provided during Instantiation process. Do this by 
specifying a Variables file.

**3. Create a Run**  
Create a Run by choosing Plan Instance and providing list of Workers for execution.

**4. Schedule or Execute a Run**  
You can either Schedule the Run for specific date/time, or execute it directly. Run will then be executed on every 
Worker simultaneously.

**5. Read the Report**  
Anytime during running of cryton the output file can be generated, which also complies to YAML format, and it contains 
list of Stages/Steps and their results.
