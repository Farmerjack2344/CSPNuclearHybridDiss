model AP1000
  "Bare-minimum AP1000: lumped NSSS heat into a four-component Rankine cycle"

  // Secondary-side DCD steam conditions (Fig 10.1-1). Enthalpies after
  // expansion and pumping are IAPWS-IF97 at those pressures.
  parameter Real Q_NSSS(unit="W") = 3414e6
    "Two steam generators at the DCD rating of 1707 MWt each";
  parameter Real p_steam(unit="Pa") = 5.571e6
    "Main steam pressure, 808 psia";
  parameter Real h1(unit="J/kg") = 2.7856e6
    "Main steam enthalpy, 1197.6 BTU/lb";
  parameter Real p_cond(unit="Pa") = 7e3
    "Hotwell pressure";
  parameter Real eta_t = 0.86
    "Lumped HP+LP isentropic turbine efficiency";
  parameter Real eta_p = 0.80
    "Feed pump isentropic efficiency";
  parameter Real tau(unit="s") = 10
    "First-order startup time constant";

  // IF97: isentropic exhaust from (p_steam, h1) to p_cond, then eta_t
  parameter Real h2s(unit="J/kg") = 1.836297e6;
  parameter Real h2(unit="J/kg") = h1 - eta_t*(h1 - h2s);
  // IF97 saturated liquid at p_cond, incompressible pump to p_steam
  parameter Real h3(unit="J/kg") = 1.633513e5;
  parameter Real v3(unit="m3/kg") = 1.0075e-3;
  parameter Real h4(unit="J/kg") = h3 + v3*(p_steam - p_cond)/eta_p;

  Real Q(unit="W", start=0, fixed=true);
  Real m_steam(unit="kg/s");
  Real P_turbine(unit="W");
  Real P_pump(unit="W");
  Real P_net(unit="W");
  Real eta_cycle;

equation
  der(Q) = (Q_NSSS - Q)/tau;
  m_steam = Q/(h1 - h4);
  P_turbine = m_steam*(h1 - h2);
  P_pump = m_steam*(h4 - h3);
  P_net = P_turbine - P_pump;
  eta_cycle = ((h1 - h2) - (h4 - h3))/(h1 - h4);

  annotation (experiment(StopTime=50, Interval=0.2, Tolerance=1e-6));
end AP1000;
