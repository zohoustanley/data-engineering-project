import os
import requests
import pandas as pd
from sqlalchemy import create_engine, text

BASE_URL = "https://geo.api.gouv.fr/departements/{code}/communes"
DB_URL = os.environ.get(
    "DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)

DDL_COMMUNES = """
CREATE TABLE IF NOT EXISTS communes (
    code              VARCHAR(5) PRIMARY KEY,
    nom               TEXT NOT NULL,
    population        INTEGER,
    code_departement  VARCHAR(3) NOT NULL
);
"""

DDL_CODES_POSTAUX = """
CREATE TABLE IF NOT EXISTS communes_codes_postaux (
    code         VARCHAR(5) NOT NULL REFERENCES communes(code),
    code_postal  VARCHAR(5) NOT NULL,
    PRIMARY KEY (code, code_postal)
);
"""

UPSERT_COMMUNES = """
INSERT INTO communes (code, nom, population, code_departement)
SELECT code, nom, population, code_departement FROM stg_communes
ON CONFLICT (code) DO UPDATE
SET nom = EXCLUDED.nom,
    population = EXCLUDED.population,
    code_departement = EXCLUDED.code_departement
WHERE (communes.nom, communes.population, communes.code_departement)
      IS DISTINCT FROM
      (EXCLUDED.nom, EXCLUDED.population, EXCLUDED.code_departement)
"""


def fetch_communes_by_departement(code_dep: str) -> pd.DataFrame:
    params = {"fields": "nom,code,codesPostaux,population,codeDepartement"}
    response = requests.get(BASE_URL.format(code=code_dep), params=params, timeout=10)
    response.raise_for_status()
    return pd.DataFrame(response.json())


def transform_communes(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df[["code", "nom", "population", "codeDepartement"]]
        .rename(columns={"codeDepartement": "code_departement"})
        .drop_duplicates(subset="code")
        .astype({"population": "Int64"})
    )


def transform_codes_postaux(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df[["code", "codesPostaux"]]
        .explode("codesPostaux")
        .rename(columns={"codesPostaux": "code_postal"})
        .dropna()
        .drop_duplicates()
    )


def init_db(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(DDL_COMMUNES))
        conn.execute(text(DDL_CODES_POSTAUX))


def load_all(communes: pd.DataFrame, codes_postaux: pd.DataFrame, engine) -> None:
    with engine.begin() as conn:  # une seule transaction pour les deux tables
        conn.execute(text("CREATE TEMP TABLE stg_communes (LIKE communes) ON COMMIT DROP"))
        communes.to_sql("stg_communes", conn, if_exists="append", index=False)
        conn.execute(text(UPSERT_COMMUNES))

        conn.execute(text("TRUNCATE TABLE communes_codes_postaux"))
        codes_postaux.to_sql("communes_codes_postaux", conn, if_exists="append", index=False)


if __name__ == "__main__":
    engine = create_engine(DB_URL)
    deps = ["75", "92", "93", "94", "95"]

    raw = pd.concat([fetch_communes_by_departement(d) for d in deps], ignore_index=True)
    communes = transform_communes(raw)
    codes_postaux = transform_codes_postaux(raw)
    print(len(communes), len(codes_postaux))

    init_db(engine)
    load_all(communes, codes_postaux, engine)