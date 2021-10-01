# ACM GitOps workflow

This repo cxontains POC for
[ACM](https://www.redhat.com/en/technologies/management/advanced-cluster-management)
GitOps.

## Contribution

This repo utilises `[pre-commit](https://pre-commit.com/)` hooks to lint code
changes. Make sure you install it before contributing to the repo.

### Installation

Following are the installation instructions for `pre-commit`. Further details
can be found [here](https://pre-commit.com/#installation).

#### Mac

```shell
brew install pre-commit
```

#### Ubuntu

```shell
pip install pre-commit
```

#### Arch Linux

```shell
pacman -S python-pre-commit
```

### Usage

`pre-commit` can run automatically on every commit. This requires to run the
following command once:

```shell
pre-commit install
```

Use the following command to run `pre-commit` manually for all files in the
repository:

```shell
pre-commit run --all-files
```

## Author

Jiri Tyr
