import rasterstats as rs
import numpy as np
import xarray as xr
import dask
import geopandas as gpd
def zonal_timeseries(dataArray, shp_loc, results_loc, feature_name, stat='mean', csv=False, netcdf=False, plot=False):
    """
    Summary: 
    Given an xarray dataArray and a shapefile, generates a timeseries of zonal statistics across n number of 
    uniquely labelled polygons. The function exports a .csv of the stats, a netcdf containing the stats, and .pdf plots.
    Requires the installation of the rasterstats module: https://pythonhosted.org/rasterstats/installation.html
    
    Inputs:
    data = xarray dataarray (note dataarray, not dataset - it is a requirement the data only have a single variable).
    shp_loc = string. Location of the shapefile used to extract the zonal timseries.
    results_loc = string. Location of the directory where results should export.
    feature_name = string. Name of attribute column in the shapefile that is of interest - used to label dataframe, plots etc.
    stat = string.  The statistic you want to extract. Options include 'count', 'max', 'median', 'min', 'std'.
    plot = Boolean. If True, function will produce pdfs of timeseries for each polygon in the shapefile.
    csv = Boolean. If True, function will export results as a .csv.
    netcdf = Boolean. If True, function will export results as a netcdf.
    
    Last modified: May 2018
    Author: Chad Burton
    
    """
    #use dask to chunk the data along the time axis in case its a very large dataset
    dataArray = dataArray.chunk(chunks = {'time':20})
    
    #create 'transform' tuple to provide ndarray with geo-referencing data. 
    one = float(dataArray.x[0])
    two = float(dataArray.y[0] - dataArray.y[1])
    three = 0.0
    four = float(dataArray.y[0])
    five = 0.0
    six = float(dataArray.x[0] - dataArray.x[1])

    transform_zonal = (one, two, three, four, five, six)

    #import shapefile, make sure its in the right projection to match the dataArray
    #and set index to the feature_name
    project_area = gpd.read_file(shp_loc)               #get the shapefile
    reproj=int(str(dataArray.crs)[5:])                  #do a little hack to get EPSG from the dataArray 
    project_area = project_area.to_crs(epsg=reproj)     #reproject shapefile to match dataArray
    project_area = project_area.set_index(feature_name) #set the index
    
    #define the general function
    def zonalStats(dataArray, stat=stat): 
        """extract the zonal statistics of all
        pixel values within each polygon"""
        stats = [] 
        for i in dataArray:
            x = rs.zonal_stats(project_area, i, transform=transform_zonal, stats=stat)    
            stats.append(x)
        #extract just the values from the results, and convert 'None' values to nan
        stats = [[t[stat] if t[stat] is not None else np.nan for t in feature] for feature in stats]
        stats = np.array(stats)
        return stats

    #use the zonal_stats functions to extract the stats:
    n = len(project_area) #number of polygons in the shapefile (defines the dimesions of the output)
    statistics = dataArray.data.map_blocks(zonalStats, chunks=(-1,n), drop_axis=1, dtype=np.float64).compute()

    #get unique identifier and timeseries data from the inputs 
    colnames = pd.Series(project_area.index.values)
    time = pd.Series(dataArray['time'].values)

    #define functions for cleaning up the results of the rasterstats operation
    def tidyresults(results):
        x = pd.DataFrame(results).T #transpose
        x = x.rename(colnames, axis='index') #rename the columns to the timestamp
        x = x.rename(columns = time)
        return x

    #place results into indexed dataframes using tidyresults function
    statistics_df = tidyresults(statistics)
    
    #convert into xarray for merging into a dataset
    stat_xr = xr.DataArray(statistics_df, dims=[feature_name, 'time'], coords={feature_name: statistics_df.index, 'time': time}, name= stat)
    
    #options for exporting results as csv, netcdf, pdf plots
    #export results as a .csv
    if csv:
        statistics_df.to_csv('{0}{1}.csv'.format(results_loc, stat))
                             
    if netcdf:
        #export out results as netcdf
        stat_xr.to_netcdf('{0}zonalstats_{1}.nc'.format(results_loc, stat), mode='w',format='NETCDF4') 

    if plot:     
        #place the data from the xarray into a list
        plot_data = []
        for i in range(0,len(stat_xr[feature_name])):
            x = stat_xr.isel([stat], **{feature_name: i})
            plot_data.append(x)

        #extract the unique names of each polygon
        feature_names = list(stat_xr[feature_name].values)

        #zip the both the data and names together as a dictionary 
        monthly_dict = dict(zip(feature_names,plot_data))

        #create a function for generating the plots
        def plotResults(dataArray, title):
            """a function for plotting up the results of the
            fractional cover change and exporting it out as pdf """
            x = dataArray.time.values
            y = dataArray.data          

            plt.figure(figsize=(15,5))
            plt.plot(x, y,'k', color='#228b22', linewidth = 1)
            plt.grid(True, linestyle ='--')
            plt.title(title)
            plt.savefig('{0}{1}.pdf'.format(results_loc, title), bbox_inches='tight')

        #loop over the dictionaries and create the plots
        {key: plotResults(monthly_dict[key], key + "_"+ stat) for key in monthly_dict} 
    
    #return the results as a dataframe
    return statistics_df
