RUN ?= run-$(shell date -u +%Y%m%dT%H%M%SZ)
MINUTES ?= 15
SECONDS_WINDOW ?= 120

.PHONY: images pki local-run local-down cloud-plan cloud-up cloud-deploy cloud-run cloud-destroy synth test lint clean

images:            ## Build the local images
	docker build -q -t pqc-nginx images/pqc-nginx
	docker build -q -t pqc-legacy-client images/legacy-client
	docker build -q -t pqc-analysis images/analysis

pki: images        ## Generate the test PKI (OpenSSL 3.5, inside the image)
	docker run --rm -v "$(CURDIR)/pki:/pki" --entrypoint sh pqc-nginx /pki/gen-pki.sh /pki/out

local-run: pki     ## Full run on local Docker:  make local-run RUN=local SECONDS_WINDOW=120
	bash scripts/local-run.sh $(RUN) $(SECONDS_WINDOW)

local-down:
	RUN=$(RUN) docker compose -f local/compose.yaml --profile probe down --remove-orphans

cloud-plan:        ## terraform plan (needs HCLOUD_TOKEN and terraform/terraform.tfvars)
	terraform -chdir=terraform init -upgrade
	terraform -chdir=terraform plan

cloud-up:          ## Create the Hetzner servers (costs money while they exist)
	terraform -chdir=terraform apply

cloud-deploy: pki  ## Copy files, build images, start services
	bash scripts/deploy.sh

cloud-run:         ## Measurement run:  make cloud-run RUN=hetzner-1 MINUTES=15
	bash scripts/run.sh $(RUN) $(MINUTES)

cloud-destroy:     ## Delete every resource this testbed created
	terraform -chdir=terraform destroy

synth:             ## Synthetic-topology experiments (paper §13.9); needs numpy and scipy
	python3 synth/run.py

test:              ## Property tests linking the Lean theorems to the code; needs pytest and hypothesis
	python3 -m pytest -q tests -p no:cacheprovider

lint:
	shellcheck -x scripts/*.sh tools/*.sh clients/*.sh pki/*.sh images/pqc-nginx/entrypoint.sh
	python3 -m py_compile tools/probe.py tools/score.py tools/analysis.py synth/engine.py synth/run.py tests/test_properties.py tests/test_extensions.py tests/gen_lean_vectors.py
	terraform -chdir=terraform fmt -check
	docker compose -f local/compose.yaml config -q
	GW_PUBLIC_IP=192.0.2.1 docker compose -f hetzner/compose.yaml --profile gw --profile lb --profile appa --profile appb --profile data --profile client --profile probe config -q

clean:
	rm -rf results/* pki/out .ssh_known_hosts
