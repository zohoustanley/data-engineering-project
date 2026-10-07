import requests
import pandas as pd
from sqlalchemy import create_engine, text

BASE_URL = "https://geo.api.gouv.fr/communes"
DB_URL = "postgresql://postgres:postgres@localhost:5432/postgres"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS communes (
    code         VARCHAR(5) NOT NULL,
    code_postal  VARCHAR(5) NOT NULL,
    nom          TEXT NOT NULL,
    population   INTEGER,
    PRIMARY KEY (code, code_postal)
);
"""

def fetch_communes(nom: str) -> pd.DataFrame:
    params = {"nom": nom, "fields": "nom,code,codesPostaux,population"}
    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    return pd.DataFrame(response.json())


def transform_communes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.explode("codesPostaux").rename(columns={"codesPostaux": "code_postal"})
    df = df[["code", "code_postal", "nom", "population"]]
    return df.astype({"population": "Int64"})


def load_communes(df: pd.DataFrame, engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        conn.execute(text("TRUNCATE TABLE communes"))
        df.to_sql("communes", conn, if_exists="append", index=False)


if __name__ == "__main__":
    engine = create_engine(DB_URL)
    raw = fetch_communes("Paris")
    clean = transform_communes(raw)
    load_communes(clean, engine)