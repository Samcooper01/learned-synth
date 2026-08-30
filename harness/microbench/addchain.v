// Long carry chains: accumulate many words. Structure = serial ripple-carry
// adders, deep and narrow.
module addchain #(parameter W = 16, parameter N = 24) (
    input  [W*N-1:0]  din,
    output [W+5-1:0]  sum
);
    integer i;
    reg [W+5-1:0] acc;
    always @* begin
        acc = 0;
        for (i = 0; i < N; i = i + 1)
            acc = acc + din[i*W +: W];
    end
    assign sum = acc;
endmodule
