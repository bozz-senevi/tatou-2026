# tatou
A web platform for pdf watermarking. This project is intended for pedagogical use, and contain security vulnerabilities. Do not deploy on an open network.

## Instructions

The following instructions are meant for a bash terminal on a Linux machine. If you are using something else, you will need to adapt them.

To clone the repo, you can simply run:

```bash
git clone https://github.com/nharrand/tatou-2026.git
```

Note that you should probably fork the repo and clone your own repo.


### Run python unit tests

```bash
cd tatou/server

# Create a python virtual environement
python3 -m venv .venv

# Activate your virtual environement
. .venv/bin/activate

# Install the necessary dependencies
python -m pip install -e ".[dev]"

# Run the unit tests
python -m pytest
```
### Measure test coverage

Some tests (the API findings tests in `test_api_findings.py`) need the running
stack, so start the stack first, then run pytest with coverage. The HTML report
is written to `artifacts/common/coverage/` (open `index.html`).

    docker compose up -d --build
    cd server
    pip install pytest pytest-cov
    TATOU_BASE=http://localhost:5000 PYTHONPATH=src python -m pytest test/ --cov=src --cov-report=html:../artifacts/common/coverage --cov-report=term-missing

A specification-to-test mapping is in `artifacts/common/specification_test_mapping.html`.
### Deploy

From the root of the directory:

```bash
# Create a file to set environement variables like passwords.
cp sample.env .env

# Edit .env and pick the passwords you want

# Rebuild the docker image and deploy the containers
docker compose up --build -d

# Monitor logs in realtime 
docker compose logs -f

# Test if the API is up
http -v :5000/healthz

# Open your browser at 127.0.0.1:5000 to check if the website is up.
```



