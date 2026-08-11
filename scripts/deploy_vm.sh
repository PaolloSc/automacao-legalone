#!/usr/bin/env bash
# Leva o codigo + a sessao do Forms pra VM Oracle e reinicia o servico.
# Rode no Git Bash, da raiz do pacote:  bash scripts/deploy_vm.sh
#
# Manda tudo que esta versionado, nao uma lista escolhida a mao: a lista
# antiga nao tinha legalone_cadastro.py e a VM ficou 2 semanas atras do repo
# sem ninguem notar. `git ls-files` tambem garante que .env e browser_data/
# (gitignored) nunca subam por engano — o state.json vai a parte, de proposito.
set -euo pipefail

VM=ubuntu@163.176.156.169
KEY=/c/Users/paollo/.oci/docuseal_vm_ssh
DEST=/home/ubuntu/pacote_automacao_legalone

[ -f browser_data/state.json ] || {
  echo "browser_data/state.json nao existe — rode antes: venv/Scripts/python.exe scripts/capturar_sessao_forms.py"
  exit 1
}

[ -z "$(git status --porcelain)" ] || {
  echo "arvore suja — commite antes, senao a VM roda o que nao esta no repo:"
  git status --short
  exit 1
}

ssh -i "$KEY" "$VM" "mkdir -p $DEST/browser_data"
scp -i "$KEY" browser_data/state.json "$VM:$DEST/browser_data/state.json"
git ls-files -z | tar --null -T - -cf - | ssh -i "$KEY" "$VM" "tar xf - -C $DEST"

ssh -i "$KEY" "$VM" "sudo systemctl restart legalone && sleep 5 && sudo systemctl is-active legalone"
echo "OK. Acompanhe: ssh -i $KEY $VM 'sudo journalctl -u legalone -f'"
