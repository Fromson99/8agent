"""References to the existing compiler and immutable Wiki authority."""


def compile_existing(compiler, repository, principal, snapshots, **options):
    """Use the host's existing compiler; editing/publishing never calls a model."""
    return compiler(repository, principal, snapshots, **options)
