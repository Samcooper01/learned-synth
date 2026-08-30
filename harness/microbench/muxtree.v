// Pure selection: a wide N:1 multiplexer. Structure = shallow balanced mux tree,
// little arithmetic.
module muxtree #(parameter W = 16, parameter SEL = 7) (
    input  [(1<<SEL)*W-1:0] din,
    input  [SEL-1:0]        sel,
    output [W-1:0]          dout
);
    assign dout = din[sel*W +: W];
endmodule
