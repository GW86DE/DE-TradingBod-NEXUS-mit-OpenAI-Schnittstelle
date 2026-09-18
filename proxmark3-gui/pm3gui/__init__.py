"""Proxmark3-GUI (Deutsch) - eine deutschsprachige, anklickbare Oberflaeche
fuer den offiziellen Proxmark3-Client.

Das Paket besteht aus:

* ``katalog``  - laedt und uebersetzt die Befehlsliste des Clients,
* ``client``   - ruft die installierte ``pm3``-Programmdatei auf,
* ``server``   - stellt Oberflaeche und JSON-Schnittstelle lokal bereit.

Start ueber ``python3 -m pm3gui`` oder ``python3 start.py``.
"""

__version__ = "0.1.0"
__all__ = ["katalog", "client", "server"]
