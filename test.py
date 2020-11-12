from aztool_topo.util.misc import round8, vectorize
import numpy as np


@vectorize
def grad2rad(angle):
    return round8((angle * np.pi) / 200)


@vectorize
def rad2grad(angle):
    return round8((angle * 200) / np.pi)


class Angle:
    def __init__(self, angle):
        self.angleG = angle if isinstance(angle, float) else np.array(angle)
        self.angleR = grad2rad(self.angleG)

    def __repr__(self):
        return f"Angle({self.angleG})"

    @staticmethod
    def round6(angle):
        return round(angle, 6)

    @property
    def rad(self):
        return self.angleR

    @property
    def grad(self):
        return self.angleG

    @property
    def cos(self):
        return np.cos(self.angleR)

    @property
    def sin(self):
        return np.sin(self.angleR)

    @property
    def count(self):
        if isinstance(self.angleG, float):
            return 1
        return len(self.angleG)

    @property
    def sum(self):
        if isinstance(self.angleG, float):
            return self.angleG
        return sum(self.angleG)

    @property
    def reverse(self):
        return self.round6(400 - self.angleG)

    def resolve(self):
        if self.angleG > 400:
            self.angleG = self.round6(self.angleG % 400)
        elif self.angleG < 0:
            self.angleG = self.round6(
                self.angleG + abs(self.angleG // 400) * 400)

        return self
