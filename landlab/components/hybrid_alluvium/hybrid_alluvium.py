import numpy as np
from landlab import Component
from .cfuncs import calculate_qs_in

class HybridAlluvium(Component):
    """
    Stream Power with Alluvium Conservation and Entrainment (SPACE)
    
    Algorithm developed by G. Tucker, summer 2016.
    Component written by C. Shobe, begun 11/28/2016.
    """
    
    _name= 'HybridAlluvium'
    
    _input_var_names = (
        'flow__receiver_node',
        'flow__upstream_node_order',
        'topographic__steepest_slope',
        'drainage_area',
        'soil__depth'
    )
    
    _output_var_names = (
        'topographic__elevation'
        'soil__depth'
    )
    
    _var_units = {
        'flow__receiver_node': '-',
        'flow__upstream_node_order': '-',
        'topographic__steepest_slope': '-',
        'drainage_area': 'm**2',
        'soil__depth': 'm',
        'topographic__elevation': 'm',
    }
    
    _var_mapping = {
        'flow__receiver_node': 'node',
        'flow__upstream_node_order': 'node',
        'topographic__steepest_slope': 'node',
        'drainage_area': 'node',
        'soil__depth': 'node',
        'topographic__elevation': 'node',
    }
    
    _var_doc = {
        'flow__receiver_node':
            'Node array of receivers (node that receives flow from current '
            'node)',
        'flow__upstream_node_order':
            'Node array containing downstream-to-upstream ordered list of '
            'node IDs',
        'topographic__steepest_slope':
            'Topographic slope at each node',
        'drainage_area':
            "Upstream accumulated surface area contributing to the node's "
            "discharge",
        'soil__depth': 
            'Depth of sediment above bedrock',
        'topographic__elevation': 
            'Land surface topographic elevation',
    }
    
    def __init__(self, grid, K_sed=None, K_br=None, F_f=None, 
                 phi=None, H_star=None, v_s=None, 
                 m_sp=None, n_sp=None, sp_crit_sed=None, 
                 sp_crit_br=None, method=None, discharge_method=None, 
                 area_field=None, discharge_field=None, **kwds):
        """Initialize the HybridAlluvium model.
        
        Parameters
        ----------
        grid : ModelGrid
            Landlab ModelGrid object
        K_sed : float
            Erodibility constant for sediment (units vary).
        K_br : float
            Erodibility constant for bedrock (units vary).
        F_f : float
            Fraction of permanently suspendable fines in bedrock [-].
        phi : float
            Sediment porosity [-].
        H_star : float
            Sediment thickness required for full entrainment [L].
        v_s : float
            Effective settling velocity for chosen grain size metric [L/T].
        m_sp : float
            Drainage area exponent (units vary)
        n_sp : float
            Slope exponent (units vary)
        sp_crit_sed : float
            Critical stream power to erode sediment [E/(TL^2)]
        sp_crit_br : float
            Critical stream power to erode rock [E/(TL^2)]
        method : string
            Either "simple_stream_power", "threshold_stream_power", or
            "stochastic_hydrology". Method for calculating sediment
            and bedrock entrainment/erosion.
        discharge_method : string
            Either "area_field" or "discharge_field". If using stochastic
            hydrology, determines whether component is supplied with
            drainage area or discharge.
        area_field : string or array
            Used if discharge_method = 'area_field'. Either field name or
            array of length(number_of_nodes) containing drainage areas [L^2].
        discharge_field : string or array
            Used if discharge_method = 'discharge_field'.Either field name or
            array of length(number_of_nodes) containing drainage areas [L^2/T].
            
        Examples
        ---------
        >>> import numpy as np
        >>> from landlab import RasterModelGrid
        >>> from landlab.components.flow_routing import FlowRouter
        >>> from landlab.components import DepressionFinderAndRouter
        >>> from landlab.components import HybridAlluvium
        >>> from landlab.components import FastscapeEroder
        >>> np.random.seed(seed = 5000)
        
        Define grid and initial topography:
            -5x5 grid with baselevel in the lower left corner
            -all other boundary nodes closed
            -Initial topography is plane tilted up to the upper right + noise
        
        >>> nr = 5
        >>> nc = 5
        >>> dx = 10
        >>> mg = RasterModelGrid((nr, nc), 10.0)
        >>> _ = mg.add_zeros('node', 'topographic__elevation')
        >>> mg['node']['topographic__elevation'] += mg.node_y/10 + \
                mg.node_x/10 + np.random.rand(len(mg.node_y)) / 10
        >>> mg.set_closed_boundaries_at_grid_edges(bottom_is_closed=True,\
                                                       left_is_closed=True,\
                                                       right_is_closed=True,\
                                                       top_is_closed=True)
        >>> mg.set_watershed_boundary_condition_outlet_id(0,\
                mg['node']['topographic__elevation'], -9999.)
        >>> fsc_dt = 100. 
        >>> hybrid_dt = 100.
        
        Instantiate Fastscape eroder, flow router, and depression finder        
        
        >>> fsc = FastscapeEroder(mg, K_sp=.001, m_sp=.5, n_sp=1)
        >>> fr = FlowRouter(mg) #instantiate
        >>> df = DepressionFinderAndRouter(mg)
        
        Burn in an initial drainage network using the Fastscape eroder:
        
        >>> for x in range(100): 
        ...     fr.run_one_step()
        ...     df.map_depressions()
        ...     flooded = np.where(df.flood_status==3)[0]
        ...     fsc.run_one_step(dt = fsc_dt, flooded_nodes=flooded)
        ...     mg.at_node['topographic__elevation'][0] -= 0.001 #uplift
        
        Add some soil to the drainage network:        
        
        >>> _ = mg.add_zeros('soil__depth', at='node', dtype=float)
        >>> mg.at_node['soil__depth'] += 0.5
        >>> mg.at_node['topographic__elevation'] += mg.at_node['soil__depth']
        
        Instantiate the hybrid component:        
        
        >>> ha = HybridAlluvium(mg, K_sed=0.00001, K_br=0.00000000001,\
                                F_f=0.5, phi=0.1, H_star=1., v_s=0.001,\
                                m_sp=0.5, n_sp = 1.0, sp_crit_sed=0,\
                                sp_crit_br=0, method='simple_stream_power',\
                                discharge_method=None, area_field=None,\
                                discharge_field=None)
                                
        Now run the hybrid component for 2000 short timesteps:                            
                                
        >>> for x in range(2000): #hybrid component loop
        ...     fr.run_one_step()
        ...     df.map_depressions()
        ...     flooded = np.where(df.flood_status==3)[0]
        ...     ha.run_one_step(dt = hybrid_dt, flooded_nodes=flooded)
        ...     mg.at_node['bedrock__elevation'][0] -= 2e-6 * hybrid_dt
        
        Now we test to see if soil depth and topography are right:
        
        >>> mg.at_node['soil__depth'] # doctest: +NORMALIZE_WHITESPACE
        array([ 0.50017567,  0.5       ,  0.5       ,  0.5       ,  0.5       ,
            0.5       ,  0.31533263,  0.43666479,  0.48101243,  0.5       ,
            0.5       ,  0.43665641,  0.43665331,  0.48040033,  0.5       ,
            0.5       ,  0.48085485,  0.48039718,  0.47769967,  0.5       ,
            0.5       ,  0.5       ,  0.5       ,  0.5       ,  0.5       ])
        
        >>> mg.at_node['topographic__elevation'] # doctest: +NORMALIZE_WHITESPACE
        array([ 0.52328045,  2.03606698,  3.0727653 ,  4.01126678,  5.06077707,
            2.08157495,  0.7439511 ,  0.87235011,  0.92742108,  6.00969486,
            3.04008677,  0.87235537,  0.87236022,  0.92797578,  7.02641123,
            4.05874171,  0.9275681 ,  0.92797857,  0.94313036,  8.05334077,
            5.05922478,  6.0409473 ,  7.07035008,  8.0038935 ,  9.01034357])
        """
        #assign class variables to grid fields; create necessary fields
        self.flow_receivers = grid.at_node['flow__receiver_node']
        self.stack = grid.at_node['flow__upstream_node_order']
        self.topographic__elevation = grid.at_node['topographic__elevation']
        self.slope = grid.at_node['topographic__steepest_slope']
        try:
            self.soil__depth = grid.at_node['soil__depth']
        except KeyError:
            self.soil__depth = grid.add_zeros(
                'soil__depth', at='node', dtype=float)
        self.link_lengths = grid._length_of_link_with_diagonals
        try:
            self.bedrock__elevation = grid.at_node['bedrock__elevation']
        except KeyError:
            self.bedrock__elevation = grid.add_zeros(
                'bedrock__elevation', at='node', dtype=float)
        self.bedrock__elevation[:] += self.topographic__elevation.copy()
        try:
            self.qs = grid.at_node['sediment__flux']
        except KeyError:
            self.qs = grid.add_zeros(
                'sediment__flux', at='node', dtype=float)
        try:
            self.q = grid.at_node['surface_water__discharge']
        except KeyError:
            self.q = grid.add_zeros(
                'surface_water__discharge', at='node', dtype=float)
                
        self._grid = grid #store grid
        
        #store other constants
        self.m_sp = float(m_sp)
        self.n_sp = float(n_sp)
        self.F_f = float(F_f)
        self.phi = float(phi)
        self.H_star = float(H_star)
        self.v_s = float(v_s)
        
        #K's and critical values can be floats, grid fields, or arrays
        if type(K_sed) is str:
            self.K_sed = self._grid.at_node[K_sed]
        elif type(K_sed) in (float, int):  # a float
            self.K_sed = float(K_sed)
        elif len(K_sed) == self.grid.number_of_nodes:
            self.K_sed = np.array(K_sed)
        else:
            raise TypeError('Supplied type of K_sed ' +
                            'was not recognised, or array was ' +
                            'not nnodes long!') 
                            
        if type(K_br) is str:
            self.K_br = self._grid.at_node[K_br]
        elif type(K_br) in (float, int):  # a float
            self.K_br = float(K_br)
        elif len(K_br) == self.grid.number_of_nodes:
            self.K_br = np.array(K_br)
        else:
            raise TypeError('Supplied type of K_br ' +
                            'was not recognised, or array was ' +
                            'not nnodes long!') 
        
        if sp_crit_sed is not None:
            if type(sp_crit_sed) is str:
                self.sp_crit_sed = self._grid.at_node[sp_crit_sed]
            elif type(sp_crit_sed) in (float, int):  # a float
                self.sp_crit_sed = float(sp_crit_sed)
            elif len(sp_crit_sed) == self.grid.number_of_nodes:
                self.sp_crit_sed = np.array(sp_crit_sed)
            else:
                raise TypeError('Supplied type of sp_crit_sed ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!') 
            
        if sp_crit_br is not None:                
            if type(sp_crit_br) is str:
                self.sp_crit_br = self._grid.at_node[sp_crit_br]
            elif type(sp_crit_br) in (float, int):  # a float
                self.sp_crit_br = float(sp_crit_br)
            elif len(sp_crit_br) == self.grid.number_of_nodes:
                self.sp_crit_br = np.array(sp_crit_br)
            else:
                raise TypeError('Supplied type of sp_crit_br ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!') 
                                
        #go through erosion methods to ensure correct hydrology
        self.method = str(method)
        self.discharge_method = discharge_method
        self.area_field = area_field
        self.discharge_field = discharge_field
        
        if self.method == 'simple_stream_power':
            self.simple_stream_power()
        elif self.method == 'threshold_stream_power':
            self.threshold_stream_power()
        elif self.method == 'stochastic_hydrology':
            self.stochastic_hydrology()
        else:
            raise ValueError('Specify erosion method (simple stream power,\
                            threshold stream power, or stochastic hydrology)!')
    #three choices for erosion methods:
    def simple_stream_power(self):
        if self.method == 'simple_stream_power' and self.discharge_method == None:
            self.q[:] = np.power(self.grid.at_node['drainage_area'], self.m_sp)
        elif self.method == 'simple_stream_power' and self.discharge_method is not None:
            self.discharge_method = str(self.discharge_method) 
            if self.discharge_method == 'drainage_area':
                if self.area_field is not None:
                    self.area_field = str(self.area_field)
                    if type(self.area_field) is str:
                        self.drainage_area = self._grid.at_node[self.area_field]
                    elif len(self.area_field) == self.grid.number_of_nodes:
                        self.drainage_area = np.array(self.area_field)
                    else:
                        raise TypeError('Supplied type of area_field ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!')  
                self.q[:] = np.power(self.drainage_area, self.m_sp)
            elif self.discharge_method == 'discharge_field':
                if self.discharge_field is not None:
                    self.discharge_field = str(self.discharge_field)
                    if type(self.discharge_field) is str:
                        self.q[:] = self._grid.at_node[self.discharge_field]
                    elif len(self.discharge_field) == self.grid.number_of_nodes:
                        self.q[:] = np.array(self.discharge_field)
                    else:
                        raise TypeError('Supplied type of discharge_field ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!')
        self.Es = self.K_sed * self.q * np.power(self.slope, self.n_sp) * \
            (1.0 - np.exp(-self.soil__depth / self.H_star))
        self.Er = self.K_br * self.q * np.power(self.slope, self.n_sp) * \
            np.exp(-self.soil__depth / self.H_star)
        self.sed_erosion_term = self.K_sed * self.q * \
            np.power(self.slope, self.n_sp)
        self.br_erosion_term = self.K_br * self.q * \
            np.power(self.slope, self.n_sp)
            
    def threshold_stream_power(self):
        if self.method == 'threshold_stream_power' and self.discharge_method == None:
            self.q[:] = np.power(self.grid.at_node['drainage_area'], self.m_sp)
        elif self.method == 'threshold_stream_power' and self.discharge_method is not None:
            self.discharge_method = str(self.discharge_method) 
            if self.discharge_method == 'drainage_area':
                if self.area_field is not None:
                    self.area_field = str(self.area_field)
                    if type(self.area_field) is str:
                        self.drainage_area = self._grid.at_node[self.area_field]
                    elif len(self.area_field) == self.grid.number_of_nodes:
                        self.drainage_area = np.array(self.area_field)
                    else:
                        raise TypeError('Supplied type of area_field ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!')  
                self.q[:] = np.power(self.drainage_area, self.m_sp)
            elif self.discharge_method == 'discharge_field':
                if self.discharge_field is not None:
                    self.discharge_field = str(str.discharge_field)
                    if type(self.discharge_field) is str:
                        self.q[:] = self._grid.at_node[self.discharge_field]
                    elif len(self.discharge_field) == self.grid.number_of_nodes:
                        self.q[:] = np.array(self.discharge_field)
                    else:
                        raise TypeError('Supplied type of discharge_field ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!')
        omega_sed = self.K_sed * self.q * \
            np.power(self.slope, self.n_sp)
        omega_br = self.K_br * self.q * \
            np.power(self.slope, self.n_sp)
        self.Es = (omega_sed - self.sp_crit_sed * (1 - np.exp(-omega_sed /\
            self.sp_crit_sed))) * \
            (1.0 - np.exp(-self.soil__depth / self.H_star))
        self.Er = (omega_br - self.sp_crit_br * (1 - np.exp(-omega_br /\
            self.sp_crit_br))) * \
            np.exp(-self.soil__depth / self.H_star)
        self.sed_erosion_term = omega_sed - self.sp_crit_sed * \
            (1 - np.exp(-omega_sed / self.sp_crit_sed))
        self.br_erosion_term = omega_br - self.sp_crit_br * \
            (1 - np.exp(-omega_br / self.sp_crit_br))
    def stochastic_hydrology(self):
        if self.method == 'stochastic_hydrology' and self.discharge_method == None:
            raise TypeError('Supply a discharge method to use stoc. hydro!')
        elif self.discharge_method is not None:
            self.discharge_method = str(self.discharge_method) 
            if self.discharge_method == 'drainage_area':
                if self.area_field is not None:
                    self.area_field = str(self.area_field)
                    if type(self.area_field) is str:
                        self.drainage_area = self._grid.at_node[self.area_field]
                    elif len(self.area_field) == self.grid.number_of_nodes:
                        self.drainage_area = np.array(self.area_field)
                    else:
                        raise TypeError('Supplied type of area_field ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!')  
                self.q[:] = np.power(self.drainage_area, self.m_sp)
            elif self.discharge_method == 'discharge_field':
                if self.discharge_field is not None:
                    self.discharge_field = str(self.discharge_field)
                    if type(self.discharge_field) is str:
                        self.q[:] = self._grid.at_node[self.discharge_field]
                    elif len(self.discharge_field) == self.grid.number_of_nodes:
                        self.q[:] = np.array(self.discharge_field)
                    else:
                        raise TypeError('Supplied type of discharge_field ' +
                                'was not recognised, or array was ' +
                                'not nnodes long!')  
            else:
                raise ValueError('Specify discharge method for stoch hydro!')
        self.Es = self.K_sed * self.q * np.power(self.slope, self.n_sp) * \
            (1.0 - np.exp(-self.soil__depth / self.H_star))
        self.Er = self.K_br * self.q * np.power(self.slope, self.n_sp) * \
            np.exp(-self.soil__depth / self.H_star)
        self.sed_erosion_term = self.K_sed * self.q * \
            np.power(self.slope, self.n_sp)
        self.br_erosion_term = self.K_br * self.q * \
            np.power(self.slope, self.n_sp)
    def run_one_step(self, dt=1.0, flooded_nodes=None, **kwds):
        """Calculate change in rock and alluvium thickness for
           a time period 'dt'.
        
        Parameters
        ----------
        dt : float
            Model timestep [T]
        flooded_nodes : array
            Indices of flooded nodes, passed from flow router
        """        
        #Choose a method for calculating erosion:
        if self.method == 'stochastic_hydrology':        
            self.stochastic_hydrology()        
        elif self.method == 'simple_stream_power':
            self.simple_stream_power()
        elif self.method == 'threshold_stream_power':
            self.threshold_stream_power()
        else:
            raise ValueError('Specify an erosion method!')
            
        self.qs_in = np.zeros(self.grid.number_of_nodes)            
            
        #iterate top to bottom through the stack, calculate qs
        # cythonized version of calculating qs_in
        calculate_qs_in(np.flipud(self.stack),
                        self.flow_receivers,
                        self.link_lengths,
                        self.q,
                        self.qs,
                        self.qs_in,
                        self.Es,
                        self.Er,
                        self.v_s,
                        self.F_f)
    
        deposition_pertime = np.zeros(self.grid.number_of_nodes)
        deposition_pertime[self.q > 0] = (self.qs[self.q > 0] * \
                                         (self.v_s / self.q[self.q > 0]))

        #now, the analytical solution to soil thickness in time:
        #need to distinguish D=kqS from all other cases to save from blowup!
        
        flooded = np.full(self._grid.number_of_nodes, False, dtype=bool)
        flooded[flooded_nodes] = True        
        
        #distinguish cases:
        blowup = deposition_pertime == self.K_sed * self.q * self.slope

        ##first, potential blowup case:
        #positive slopes, not flooded
        self.soil__depth[(self.q > 0) & (blowup==True) & (self.slope > 0) & \
            (flooded==False)] = self.H_star * \
            np.log((self.sed_erosion_term[(self.q > 0) & (blowup==True) & \
            (self.slope > 0) & (flooded==False)] / self.H_star) * dt + \
            np.exp(self.soil__depth[(self.q > 0) & (blowup==True) & \
            (self.slope > 0) & (flooded==False)] / self.H_star))
        #positive slopes, flooded
        self.soil__depth[(self.q > 0) & (blowup==True) & (self.slope > 0) & \
            (flooded==True)] = (deposition_pertime[(self.q > 0) & \
            (blowup==True) & (self.slope > 0) & (flooded==True)] / (1 - self.phi)) * dt   
        #non-positive slopes, not flooded
        self.soil__depth[(self.q > 0) & (blowup==True) & (self.slope <= 0) & \
            (flooded==False)] += (deposition_pertime[(self.q > 0) & \
            (blowup==True) & (self.slope <= 0) & (flooded==False)] / \
            (1 - self.phi)) * dt    
        
        ##more general case:
        #positive slopes, not flooded
        self.soil__depth[(self.q > 0) & (blowup==False) & (self.slope > 0) & \
            (flooded==False)] = self.H_star * \
            np.log((1 / ((deposition_pertime[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)] * (1 - self.phi)) / \
            (self.sed_erosion_term[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)]) - 1)) * \
            (np.exp((deposition_pertime[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)] * (1 - self.phi) - \
            (self.sed_erosion_term[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)]))*(dt / self.H_star)) * \
            (((deposition_pertime[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)] * (1 - self.phi) / \
            (self.sed_erosion_term[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)])) - 1) * \
            np.exp(self.soil__depth[(self.q > 0) & (blowup==False) & \
            (self.slope > 0) & (flooded==False)] / self.H_star)  + 1) - 1))
        #places where slope <= 0 but not flooded:
        self.soil__depth[(self.q > 0) & (blowup==False) & (self.slope <= 0) & \
            (flooded==False)] += (deposition_pertime[(self.q > 0) & \
            (blowup==False) & (self.slope <= 0) & (flooded==False)] / \
            (1 - self.phi)) * dt     
        #flooded nodes:        
        self.soil__depth[(self.q > 0) & (blowup==False) & (flooded==True)] += \
            (deposition_pertime[(self.q > 0) & (blowup==False) & \
            (flooded==True)] / (1 - self.phi)) * dt     

        self.bedrock__elevation[self.q > 0] += dt * \
            (-self.br_erosion_term[self.q > 0] * \
            (np.exp(-self.soil__depth[self.q > 0] / self.H_star)))

        #finally, determine topography by summing bedrock and soil
        self.topographic__elevation[:] = self.bedrock__elevation + \
            self.soil__depth 

    def rock_alluv_func(x, H0, d, s, a, etad, Hstar, R0, r):
        """Functions of x0 (H) and x1 (R) that should evaluate to zero."""

        f1 = (((x[0] - H0) - d) + s * a * ((x[0] + x[1]) - etad)
             * (1.0 - np.exp( -x[0] / Hstar)))
        f2 = (x[1] - R0) + r * a * ((x[1] + x[0]) - etad) * np.exp( -x[0] / Hstar)
        return [f1, f2]

    def experimental_local_solver(self, dt=1.0):
        """Experimental solver that sweeps downstream, then upstream."""
        from scipy.optimize import fsolve

        self.qs_in = np.zeros(self.grid.number_of_nodes)            
        self.qs_out = np.zeros(self.grid.number_of_nodes)            
    
        # (for efficiency, we'd want to pre-allocate qs_in and qs_out init,
        # and then zero out qs_in here)
        
        # get references to useful fields
        r = self.grid.at_node['flow__receiver_node']
        node_stack = self.grid.at_node['flow__upstream_node_order']
        S = self.grid.at_node['topographic__steepest_slope']
        a = self.grid.at_node['drainage_area']
        H = self.grid.at_node['soil__depth']
        z = self.grid.at_node['topographic__elevation']

        # Sweep downstream, accumulating qs_in and qs_out
        nn = self.grid.number_of_nodes
        for i in range(nn - 1, -1, -1):
            src = node_stack[i]
            dest = r[src]
            if src != dest:
                ehhstar = np.exp(-H[src] / self.H_star)
                amsn = a[src]**0.5 * S[src]
                Es = self.K_sed * amsn * (1.0 - ehhstar)
                Er = self.K_br * amsn * ehhstar
                E = Es + Er
                print(str(i) + ' ' + str(Es) + ' ' + str(Er) + ' ' + str(E))
                print(' A^1/2 S = ' + str(amsn))
                eav = E * a[src] / self.v_s
                elam = np.exp(-self.v_s * self.grid._dx * self.grid._dx
                              / a[src])
                print(' len scale=' + str(a[src]/(self.grid._dx*self.v_s)))
                self.qs_out[src] = (self.qs_in[src] * elam
                                    + (1.0 - elam) * eav)
                print(' qs_in = ' + str(self.qs_in[src]))
                print(' qs_out = ' + str(self.qs_out[src]))
                self.qs_in[dest] += self.qs_out[src]

        # Sweep upstream, finding the joint solution for alluvium and rock
        # simultaneously using fsolve
        print('\nUpstream loop here:')
        for i in range(0, nn):
            src = node_stack[i]
            dest = r[src]
            if src != dest:
                print((src, dest))

                d = (self.v_s * self.qs_in[src] * dt) / a[src]
                aa = (self.a[src] ** 0.5) * dt / self.grid._dx
                R0 = z[src] - H[src]

                print(' old H: ' + str(H[src]) + ' old R: ' + str(R0) + ' old z: ' + str(z[src]))
                x0 = np.array([H[src], R0])
                (H, R) = fsolve(self.rock_alluv_func, x0,
                                args=(H[src], d, self.K_sed, aa, z[dest],
                                      self.H_star, R0, self.K_br))
                print(' new H: ' + str(H) + ' new R: ' + str(R) + ' new z: ' + str(R+H))
        