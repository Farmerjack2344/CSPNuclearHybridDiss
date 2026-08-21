class MoltenSalt():
    def __int__(self):
        pass

    def cp(self,Temp):
        return (41443 + (0.172 * Temp))


    def rho_func(self,Temp):
        return (2090 - (0.636 * Temp))


    def k(self,Temp):
        return (0.443 + (1.9e-4 * Temp))


    def d_viscosity(self,Temp):
        return ((22.714 - (0.12 * Temp) + (2.281e-4 * (Temp**2)) - (1.474e-7 * (Temp**3))) /1000)