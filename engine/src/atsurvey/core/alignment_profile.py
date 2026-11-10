"""Vertical profile of a road (μηκοτομή ερυθράς): grades between the PVIs and symmetric
parabolic vertical curves (AASHTO *Green Book* §3.4.6; ΟΜΟΕ-Χ):

    z(x) = z_PVC + g₁ x + (g₂ − g₁) x² / 2L,   grade(x) = g₁ + (g₂ − g₁) x / L,

x measured from the PVC = PVI − L/2. The parameter H = L / |g₂ − g₁| is the radius of curvature
at the crest or sag; the mid-ordinate at the PVI is (g₂ − g₁) L / 8.
"""

from __future__ import annotations

import bisect

from .alignment_models import GradeRow, ProfileResult, VerticalCurveRow, VerticalProfile
from .issues import IssueSink

LENGTH_EPS = 1e-6


class Profile:
    """Vertical profile: grades between PVIs and symmetric parabolic vertical curves."""

    def __init__(self, prof: VerticalProfile) -> None:
        self.sink = IssueSink()
        p = prof.pvis
        self.names = [q.name or f"V{i}" for i, q in enumerate(p)]
        self.ch = [q.chainage for q in p]
        self.z = [q.elevation for q in p]
        for i in range(len(p) - 1):
            if self.ch[i + 1] - self.ch[i] < LENGTH_EPS:
                raise ValueError(
                    f"Profile vertices must have increasing chainages ({self.names[i]} → "
                    f"{self.names[i + 1]})"
                )
        self.g = [
            (self.z[i + 1] - self.z[i]) / (self.ch[i + 1] - self.ch[i]) for i in range(len(p) - 1)
        ]
        self.lengths = [0.0] * len(p)
        for j in range(1, len(p) - 1):
            dg = self.g[j] - self.g[j - 1]
            q = p[j]
            if q.length is not None:
                self.lengths[j] = q.length
            elif q.radius is not None:
                self.lengths[j] = q.radius * abs(dg)
            if abs(dg) < 1e-12:
                self.lengths[j] = 0.0
        self._check()

    @property
    def errors(self) -> list[str]:
        return [i.message for i in self.sink.items if i.severity == "error"]

    def _check(self) -> None:
        reach = self.ch[0]
        prev = self.names[0]
        for j in range(1, len(self.ch)):
            half = self.lengths[j] / 2.0
            if self.ch[j] - half < reach - 1e-9:
                self.sink.error(
                    "ALIGN_VERTICAL_OVERLAP",
                    f"Vertical curves at {prev} and {self.names[j]} overlap",
                    vertex_a=prev,
                    vertex_b=self.names[j],
                )
            reach = self.ch[j] + half
            prev = self.names[j]
        if reach > self.ch[-1] + 1e-9:
            self.sink.error(
                "ALIGN_VERTICAL_OVERLAP",
                f"The vertical curve at {self.names[-2]} runs past the end of the profile",
                vertex_a=self.names[-2],
                vertex_b=self.names[-1],
            )

    def at(self, chainage: float) -> tuple[float, float] | None:
        """(elevation, grade) at a chainage, or None outside the profile."""
        if chainage < self.ch[0] - 1e-9 or chainage > self.ch[-1] + 1e-9:
            return None
        k = min(max(bisect.bisect_right(self.ch, chainage) - 1, 0), len(self.ch) - 2)
        for j in (k, k + 1):
            if 0 < j < len(self.ch) - 1 and self.lengths[j] > 0.0:
                L = self.lengths[j]
                pvc = self.ch[j] - L / 2.0
                if pvc - 1e-12 <= chainage <= pvc + L + 1e-12:
                    g1, g2 = self.g[j - 1], self.g[j]
                    x = chainage - pvc
                    z0 = self.z[j] - g1 * L / 2.0
                    return z0 + g1 * x + (g2 - g1) * x * x / (2.0 * L), g1 + (g2 - g1) * x / L
        return self.z[k] + self.g[k] * (chainage - self.ch[k]), self.g[k]

    def result(self) -> ProfileResult:
        grades = [
            GradeRow(from_chainage=self.ch[i], to_chainage=self.ch[i + 1], grade=self.g[i])
            for i in range(len(self.g))
        ]
        curves = []
        for j in range(1, len(self.ch) - 1):
            g1, g2, L = self.g[j - 1], self.g[j], self.lengths[j]
            dg = g2 - g1
            ext_ch = ext_z = None
            if L > 0.0 and g1 * g2 < 0.0:
                x = -g1 * L / dg
                ext_ch = self.ch[j] - L / 2.0 + x
                ext_z = self.z[j] - g1 * L / 2.0 + g1 * x + dg * x * x / (2.0 * L)
            curves.append(
                VerticalCurveRow(
                    name=self.names[j],
                    chainage=self.ch[j],
                    elevation=self.z[j],
                    kind="none" if abs(dg) < 1e-12 else ("crest" if dg < 0 else "sag"),
                    length=L,
                    radius=L / abs(dg) if L > 0.0 and abs(dg) > 1e-12 else None,
                    pvc_chainage=self.ch[j] - L / 2.0,
                    pvc_elevation=self.z[j] - g1 * L / 2.0,
                    pvt_chainage=self.ch[j] + L / 2.0,
                    pvt_elevation=self.z[j] + g2 * L / 2.0,
                    extreme_chainage=ext_ch,
                    extreme_elevation=ext_z,
                )
            )
        return ProfileResult(grades=grades, curves=curves)
