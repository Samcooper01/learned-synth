// One-hot decode: high fanout from few inputs to many outputs. Structure =
// broad AND fan-out, minimal depth.
module decoder #(parameter SEL = 9) (
    input  [SEL-1:0]        sel,
    input                   en,
    output [(1<<SEL)-1:0]   dout
);
    assign dout = en ? ({{((1<<SEL)-1){1'b0}}, 1'b1} << sel) : {(1<<SEL){1'b0}};
endmodule
