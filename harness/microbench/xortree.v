// Linear (crypto-like): wide XOR reduction of many words. Structure = balanced
// XOR tree, no carries, high symmetry.
module xortree #(parameter W = 32, parameter N = 48) (
    input  [W*N-1:0]  din,
    output [W-1:0]    dout
);
    integer i;
    reg [W-1:0] acc;
    always @* begin
        acc = 0;
        for (i = 0; i < N; i = i + 1)
            acc = acc ^ din[i*W +: W];
    end
    assign dout = acc;
endmodule
