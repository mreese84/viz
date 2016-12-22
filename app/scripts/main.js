'use strict';

// set the dimensions and margins of the graph
var margin = {top: 20, right: 20, bottom: 30, left: 50},
  width = 1500 - margin.left - margin.right,
  height = 300 - margin.top - margin.bottom;

// parse the date / time
var parseTime = d3.utcParse("%Y-%m-%dT%H:%M:%SZ");

// set the ranges
var x = d3.scaleTime().range([0, width]);
var y = d3.scaleLinear().range([height, 0]);

// define the area
var elevationarea = d3.area()
  .x(function(d) { return x(d.time); })
  .y1(function(d) { return y(d.ele); })
  .y0(y(0));

// append the svg obgect to the body of the page
// appends a 'group' element to 'svg'
// moves the 'group' element to the top left margin
var svg = d3.select("#cycling-vis").append("svg")
  .attr("width", width + margin.left + margin.right)
  .attr("height", height + margin.top + margin.bottom)
  .append("g")
    .attr("transform",
    "translate(" + margin.left + "," + margin.top + ")");

// Get the data
d3.csv("data/los-lunas.csv", function(error, data) {
  if (error) throw error;

  // format the data
  data.forEach(function(d) {
    d.time = parseTime(d.time);
    d.ele = +d.ele;
  });

  // Scale the range of the data. Set minimum ele to 1400m.
  x.domain(d3.extent(data, function(d) { return d.time; }));
  y.domain([1400, d3.max(data, function(d) { return d.ele; })]);

  // Add the elevationarea path.
  svg.append("path")
    .data([data])
    .attr("class", "line")
    .attr("d", elevationarea);

  // Add the X Axis
  svg.append("g")
    .attr("transform", "translate(0," + height + ")")
    .call(d3.axisBottom(x));

  // Add the Y Axis
  svg.append("g")
    .call(d3.axisLeft(y));
});
