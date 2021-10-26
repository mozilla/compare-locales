from setuptools import setup

setup(
    name="cl_ext.lang",
    version="0.1.0",
    author="Axel Hecht",
    author_email="axel@mozilla.com",
    description=".lang parser for compare-locales",
    platforms=["any"],
    python_requires='>=3.7, <4',
    package_dir={"": "src"},
    packages=['cl_ext', 'cl_ext.lang'],
    install_requires=[
        "parsimonious",
        "compare_locales",
    ]
)
