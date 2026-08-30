// Deep, regular arithmetic: a combinational multiplier. Structure = tall
// partial-product / carry-save network, high reconvergence.
module mult #(parameter W = 18) (
    input  [W-1:0]     a,
    input  [W-1:0]     b,
    output [2*W-1:0]   p
);
    assign p = a * b;
endmodule
