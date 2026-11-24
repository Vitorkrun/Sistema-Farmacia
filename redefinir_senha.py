#!/usr/bin/env python3
"""Redefine a senha de um usuario (use se esquecer). Uso: python redefinir_senha.py"""
import sqlite3, os, getpass
import servidor
c = sqlite3.connect(servidor.BANCO)
us = c.execute("SELECT id, nome, perfil FROM usuarios ORDER BY id").fetchall()
for u in us: print(f"{u[0]} - {u[1]} ({u[2]})")
uid = int(input("Numero do usuario: "))
s = getpass.getpass("Nova senha (min. 4 caracteres): ")
assert len(s) >= 4, "Senha muito curta."
c.execute("UPDATE usuarios SET senha_hash=? WHERE id=?", (servidor.hash_senha(s), uid)); c.commit()
print("Senha alterada.")
