import setuptools

PYTHON_SRC = 'src/main/python'

with open('src/main/python/dlpx/virtualization/_internal/VERSION') as fp:
    version = fp.read().strip()

install_requires = [
  "click >= 7.0",
  "click-configfile == 0.2.3",
  "enum34 >= 1.1.6",
  "flake8 >= 3.6",
  "jinja2 >= 2.10",
  "jsonschema >= 3",
  "protobuf == 3.6.1",
  "pyyaml >= 3",
  "requests >= 2.21.0",
  "typing;python_version < '3.5'",
]

setuptools.setup(name='dvp-tools',
                 version=version,
                 install_requires=install_requires,
                 package_dir={'': PYTHON_SRC},
                 packages=setuptools.find_packages(PYTHON_SRC),
)
