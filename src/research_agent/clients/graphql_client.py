from dotenv import load_dotenv
import os
from graphql_client.client import Client

load_dotenv()

def make_client_from_env() -> Client:
    graphql_auth_token = os.getenv("GRAPHQL_AUTH_TOKEN")
    graphql_url = os.getenv("GRAPHQL_LOCAL_URL") or "http://localhost:4000/graphql"
    if graphql_url.startswith("localhost"):
        graphql_url = "http://" + graphql_url

    return Client(
        url=graphql_url,
        headers={"Authorization": f"Bearer {graphql_auth_token}"},
    )
