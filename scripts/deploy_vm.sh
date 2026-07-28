#!/usr/bin/env bash
# Leva sessao do Forms + fix de erro pra VM Oracle e reinicia o servico.
# Rode no Git Bash, da raiz do pacote:  bash scripts/deploy_vm.sh
set -euo pipefail

VM=ubuntu@163.176.156.169
KEY=/c/Users/paollo/.oci/docuseal_vm_ssh
DEST=/home/ubuntu/pacote_automacao_legalone

[ -f browser_data/state.json ] || {
  echo "browser_data/state.json nao existe — rode antes: venv/Scripts/python.exe scripts/capturar_sessao_forms.py"
  exit 1
}

ssh -i "$KEY" "$VM" "mkdir -p $DEST/browser_data"
scp -i "$KEY" browser_data/state.json "$VM:$DEST/browser_data/state.json"
scp -i "$KEY" forms_extractor.py automacao_legalone_completa.py "$VM:$DEST/"
scp -i "$KEY" tests/test_forms_sem_sessao.py "$VM:$DEST/tests/"

ssh -i "$KEY" "$VM" "sudo systemctl restart legalone && sleep 5 && sudo systemctl is-active legalone"
echo "OK. Acompanhe: ssh -i $KEY $VM 'sudo journalctl -u legalone -f'"
