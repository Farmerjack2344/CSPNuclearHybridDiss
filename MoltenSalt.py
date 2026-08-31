
class MoltenSalt:
    """
        Solar Salt (60% NaNO3 / 40% KNO3) has no CoolProp fluid string, so it can't be
        placed on a TESPy connection. This module tracks the salt-side mass balance and
        state of charge (SoC) externally, using bulk cp from the MoltenSalt property
        class (Zavoico 2001 correlations).
    """
    def cp(self, temp):
        return 1443 + (0.172 * temp)

    def rho(self, temp):
        return  2090 - (0.636 * temp)

    def k(self, temp):
        return 0.443 + (1.9e-4 * temp)

    def mu(self, temp):
        """

        :param temp: temperature
        :return:Dynamic viscosity
        """
        return 2.2714e-3 - (1.20e-4 * temp) + (2.281e-7 * (temp ** 2)) - (1.474e-10 * (temp ** 3))

