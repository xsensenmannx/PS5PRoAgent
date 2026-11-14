"""Shop-Namen des Radars, Stand v1.4.

Bewusst als eigene Datei: Die Hilfe-App wird getrennt gepackt und darf nicht
von ``scan_core`` abhängen. Der Test ``test_shops_passen_zu_scan_core``
vergleicht die Liste im Repository mit der echten Quelle und schlägt an, wenn
beide auseinanderlaufen.
"""

SHOPS = (
    # Deutschland
    "PS Direct DE",
    "Amazon DE",
    "MediaMarkt DE",
    "Saturn DE",
    "Alternate DE",
    "Otto DE",
    "Cyberport DE",
    "Euronics",
    "Expert",
    "Mueller",
    "Notebooksbilliger",
    "Coolblue DE",
    "Conrad DE",
    "Kaufland",
    "GameStop DE",
    "Proshop DE",
    "Computeruniverse",
    "Galaxus DE",
    "Alza DE",
    "Spielekauf.de",
    "Geizhals DE",
    "Aetka DE",
    # Oesterreich
    "PS Direct AT",
    "MediaMarkt AT",
    "Saturn AT",
    "Libro AT",
    "Alza AT",
    "Cyberport AT",
    "Hartlauer AT",
    "Electronic4you",
    "Coolblue AT",
    "Conrad AT",
    "Quelle AT",
    "Universal AT",
    "Otto AT",
    "GameStop AT",
    "Proshop AT",
    "Amazon AT",
    "Gameware AT",
    "shöpping.at",
    "Geizhals AT",
    "Computerexpert AT",
)

SHOP_COUNT = len(SHOPS)
