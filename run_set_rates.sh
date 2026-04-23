#!/bin/bash
# Запуск скрипта выставления тарифов в conda окружении pms
cd "$(dirname "$0")"
/root/miniconda3/envs/pms/bin/python set_rates.py "$@"
