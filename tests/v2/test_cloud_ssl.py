from app.cloud.http import SSL_CONTEXT


def test_cloud_https_has_own_root_certificates():
    # без них в Mac-сборке вход в облако отвечал «нет интернета»
    assert SSL_CONTEXT.cert_store_stats()["x509_ca"] > 50
