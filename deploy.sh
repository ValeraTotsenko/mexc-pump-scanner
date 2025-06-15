#!/usr/bin/env bash
sudo apt update && sudo apt -y install docker.io docker-compose
git clone https://github.com/you/mexc-pump-scanner.git
cd mexc-pump-scanner
cp .env.example .env
sudo docker-compose up -d --build
