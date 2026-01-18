from setuptools import setup, find_packages

setup(
    name="etl-database-schema",
    version="0.4.3",
    packages=find_packages(),
    install_requires=[
        "django>=4.0",
        "python-dotenv>=1.0.0",
        "django-extensions>=4.1",
        "python-json-logger==4.0.0",
        "djangosaml2>=1.10.1",
        "django-otp>=1.6.0",
        "psycopg2-binary>=2.9.10",
        "pillow>=11.2.1",
        "pyopenssl>=25.1.0",
        "redis>=6.2.0",
        "psutil>=7.0.0",
        "qrcode>=6.1",
        "django-two-factor-auth>=1.17.0",
        "beautifulsoup4>=4.13.4",
        "lxml>=5.4.0",
        "django-debug-toolbar>=5.2.0",
    ],
    include_package_data=True,
    package_data={"etl_database_schema": ["templates/**/*", "static/**/*"]},
)
