"""Shared cat vocabulary used by the active runtime."""
from enum import Enum


class Breed(str, Enum):
    ORANGE_TABBY = "orange_tabby"
    BLACK = "black"
    SIAMESE = "siamese"
    BRITISH_GREY = "british_shorthair_grey"
    CALICO = "calico"
    WHITE = "white"
